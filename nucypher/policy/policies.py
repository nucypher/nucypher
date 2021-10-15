"""
This file is part of nucypher.

nucypher is free software: you can redistribute it and/or modify
it under the terms of the GNU Affero General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

nucypher is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU Affero General Public License for more details.

You should have received a copy of the GNU Affero General Public License
along with nucypher.  If not, see <https://www.gnu.org/licenses/>.
"""


from abc import ABC, abstractmethod
from typing import Tuple, Sequence, Optional, Iterable, Dict, Type

import maya
from eth_typing.evm import ChecksumAddress

from nucypher.core import HRAC, TreasureMap, Arrangement, ArrangementResponse

from nucypher.crypto.powers import DecryptingPower
from nucypher.crypto.umbral_adapter import PublicKey, VerifiedKeyFrag, Signature
from nucypher.network.middleware import RestMiddleware
from nucypher.policy.reservoir import (
    make_federated_staker_reservoir,
    MergedReservoir,
    PrefetchStrategy,
    make_decentralized_staker_reservoir
)
from nucypher.policy.revocation import RevocationKit
from nucypher.utilities.concurrency import WorkerPool
from nucypher.utilities.logging import Logger


class Policy(ABC):
    """
    An edict by Alice, arranged with n Ursulas, to perform re-encryption for a specific Bob.
    """

    log = Logger("Policy")

    class PolicyException(Exception):
        """Base exception for policy exceptions"""

    class NotEnoughUrsulas(PolicyException):
        """
        Raised when a Policy has been used to generate Arrangements with Ursulas insufficient number
        such that we don't have enough KeyFrags to give to each Ursula.
        """

    class EnactmentError(PolicyException):
        """Raised if one or more Ursulas failed to enact the policy."""

    class Unpaid(PolicyException):
        """Raised when a worker expects policy payment but receives none."""

    class Unknown(PolicyException):
        """Raised when a worker cannot find a published policy for a given policy ID"""

    class Inactive(PolicyException):
        """Raised when a worker is requested to perform re-encryption for a disabled policy"""

    class Expired(PolicyException):
        """Raised when a worker is requested to perform re-encryption for an expired policy"""

    class Unauthorized(PolicyException):
        """Raised when Bob is not authorized to request re-encryptions from Ursula.."""

    class Revoked(Unauthorized):
        """Raised when a policy is revoked has been revoked access"""

    def __init__(self,
                 publisher: 'Alice',
                 label: bytes,
                 expiration: maya.MayaDT,
                 bob: 'Bob',
                 kfrags: Sequence[VerifiedKeyFrag],
                 public_key: PublicKey,
                 threshold: int,
                 ):

        """
        :param kfrags:  A list of KeyFrags to distribute per this Policy.
        :param label: The identity of the resource to which Bob is granted access.
        """

        self.threshold = threshold
        self.shares = len(kfrags)
        self.publisher = publisher
        self.label = label
        self.bob = bob
        self.kfrags = kfrags
        self.public_key = public_key
        self.expiration = expiration

        """
        # TODO: #180 - This attribute is hanging on for dear life.
        After 180 is closed, it can be completely deprecated.

        The "hashed resource authentication code".

        A hash of:
        * Alice's public key
        * Bob's public key
        * the label

        Alice and Bob have all the information they need to construct this.
        'Ursula' does not, so we share it with her.
        """
        self.hrac = HRAC.derive(publisher_verifying_key=self.publisher.stamp.as_umbral_pubkey(),
                                bob_verifying_key=self.bob.stamp.as_umbral_pubkey(),
                                label=self.label)

    def __repr__(self):
        return f"{self.__class__.__name__}:{bytes(self.hrac).hex()[:6]}"

    @abstractmethod
    def _make_reservoir(self, handpicked_addresses: Sequence[ChecksumAddress]) -> MergedReservoir:
        """
        Builds a `MergedReservoir` to use for drawing addresses to send proposals to.
        """
        raise NotImplementedError

    def _enact_arrangements(self, arrangements: Dict['Ursula', Arrangement]):
        pass

    def _propose_arrangement(self,
                             address: ChecksumAddress,
                             network_middleware: RestMiddleware,
                             ) -> Tuple['Ursula', Arrangement]:
        """
        Attempt to propose an arrangement to the node with the given address.
        """

        if address not in self.publisher.known_nodes:
            raise RuntimeError(f"{address} is not known")

        ursula = self.publisher.known_nodes[address]
        arrangement = Arrangement(publisher_verifying_key=self.publisher.stamp.as_umbral_pubkey(),
                                  expiration_epoch=self.expiration.epoch)

        self.log.debug(f"Proposing arrangement {arrangement} to {ursula}")
        negotiation_response = network_middleware.propose_arrangement(ursula, arrangement)
        status = negotiation_response.status_code

        if status == 200:
            # TODO: What to do in the case of invalid signature?
            # Verify that the sampled ursula agreed to the arrangement.
            response = ArrangementResponse.from_bytes(negotiation_response.content)
            self.publisher.verify_from(stranger=ursula,
                                       message=bytes(arrangement),
                                       signature=response.signature)
            self.log.debug(f"Arrangement accepted by {ursula}")
        else:
            message = f"Proposing arrangement to {ursula} failed with {status}"
            self.log.debug(message)
            raise RuntimeError(message)

        # We could just return the arrangement and get the Ursula object
        # from `known_nodes` later, but when we introduce slashing in FleetSensor,
        # the address can already disappear from `known_nodes` by that time.
        return ursula, arrangement

    def _make_arrangements(self,
                           network_middleware: RestMiddleware,
                           handpicked_ursulas: Optional[Iterable['Ursula']] = None,
                           timeout: int = 10,
                           ) -> Dict['Ursula', Arrangement]:
        """
        Pick some Ursula addresses and send them arrangement proposals.
        Returns a dictionary of Ursulas to Arrangements if it managed to get `shares` responses.
        """

        if handpicked_ursulas is None:
            handpicked_ursulas = []
        handpicked_addresses = [ChecksumAddress(ursula.checksum_address) for ursula in handpicked_ursulas]

        reservoir = self._make_reservoir(handpicked_addresses)
        value_factory = PrefetchStrategy(reservoir, self.shares)

        def worker(address):
            return self._propose_arrangement(address, network_middleware)

        self.publisher.block_until_number_of_known_nodes_is(self.shares, learn_on_this_thread=True, eager=True)

        worker_pool = WorkerPool(worker=worker,
                                 value_factory=value_factory,
                                 target_successes=self.shares,
                                 timeout=timeout,
                                 stagger_timeout=1,
                                 threadpool_size=self.shares)
        worker_pool.start()
        try:
            successes = worker_pool.block_until_target_successes()
        except (WorkerPool.OutOfValues, WorkerPool.TimedOut):
            # It's possible to raise some other exceptions here,
            # but we will use the logic below.
            successes = worker_pool.get_successes()
        finally:
            worker_pool.cancel()
            worker_pool.join()

        accepted_arrangements = {ursula: arrangement for ursula, arrangement in successes.values()}
        failures = worker_pool.get_failures()

        accepted_addresses = ", ".join(ursula.checksum_address for ursula in accepted_arrangements)

        if len(accepted_arrangements) < self.shares:

            rejected_proposals = "\n".join(f"{address}: {value}" for address, (type_, value, traceback) in failures.items())

            self.log.debug(
                "Could not find enough Ursulas to accept proposals.\n"
                f"Accepted: {accepted_addresses}\n"
                f"Rejected:\n{rejected_proposals}")

            raise self._not_enough_ursulas_exception()
        else:
            self.log.debug(f"Finished proposing arrangements; accepted: {accepted_addresses}")

        return accepted_arrangements

    def enact(self,
              network_middleware: RestMiddleware,
              handpicked_ursulas: Optional[Iterable['Ursula']] = None,
              ) -> 'EnactedPolicy':
        """
        Attempts to enact the policy, returns an `EnactedPolicy` object on success.
        """

        # TODO: Why/is this needed here?
        # Workaround for `RuntimeError: Learning loop is not running.  Start it with start_learning().`
        if not self.publisher._learning_task.running:
            self.publisher.start_learning_loop()

        arrangements = self._make_arrangements(network_middleware=network_middleware,
                                               handpicked_ursulas=handpicked_ursulas)

        self._enact_arrangements(arrangements)

        assigned_kfrags = {
            ursula.checksum_address: (ursula.public_keys(DecryptingPower), vkfrag)
            for ursula, vkfrag in zip(arrangements, self.kfrags)}

        treasure_map = TreasureMap.construct_by_publisher(hrac=self.hrac,
                                                          policy_encrypting_key=self.public_key,
                                                          signer=self.publisher.stamp.as_umbral_signer(),
                                                          assigned_kfrags=assigned_kfrags,
                                                          threshold=self.threshold)

        enc_treasure_map = treasure_map.encrypt(signer=self.publisher.stamp.as_umbral_signer(),
                                                recipient_key=self.bob.public_keys(DecryptingPower))

        # TODO: Signal revocation without using encrypted kfrag
        revocation_kit = RevocationKit(treasure_map=treasure_map, signer=self.publisher.stamp)

        enacted_policy = EnactedPolicy(self.hrac,
                                       self.label,
                                       self.public_key,
                                       treasure_map.threshold,
                                       enc_treasure_map,
                                       revocation_kit,
                                       self.publisher.stamp.as_umbral_pubkey())

        return enacted_policy

    @abstractmethod
    def _not_enough_ursulas_exception(self) -> Type[Exception]:
        """
        Returns an exception to raise when there were not enough Ursulas
        to distribute arrangements to.
        """
        raise NotImplementedError

    @abstractmethod
    def _make_enactment_payload(self, kfrag: VerifiedKeyFrag) -> bytes:
        """
        Serializes a given kfrag and policy publication transaction to send to Ursula.
        """
        raise NotImplementedError


class FederatedPolicy(Policy):

    def _not_enough_ursulas_exception(self):
        return Policy.NotEnoughUrsulas

    def _make_reservoir(self, handpicked_addresses):
        return make_federated_staker_reservoir(known_nodes=self.publisher.known_nodes,
                                               include_addresses=handpicked_addresses)

    def _make_enactment_payload(self, kfrag) -> bytes:
        return bytes(kfrag)


class BlockchainPolicy(Policy):
    """
    A collection of n Arrangements representing a single Policy
    """

    class InvalidPolicyValue(ValueError):
        pass

    class NotEnoughBlockchainUrsulas(Policy.NotEnoughUrsulas):
        pass

    def __init__(self,
                 value: int,
                 rate: int,
                 payment_periods: int,
                 *args,
                 **kwargs):

        super().__init__(*args, **kwargs)

        self.payment_periods = payment_periods
        self.value = value
        self.rate = rate

        self._validate_fee_value()

    def _not_enough_ursulas_exception(self):
        return BlockchainPolicy.NotEnoughBlockchainUrsulas

    def _validate_fee_value(self) -> None:
        rate_per_period = self.value // self.shares // self.payment_periods  # wei
        recalculated_value = self.payment_periods * rate_per_period * self.shares
        if recalculated_value != self.value:
            raise ValueError(f"Invalid policy value calculation - "
                             f"{self.value} can't be divided into {self.shares} staker payments per period "
                             f"for {self.payment_periods} periods without a remainder")

    @staticmethod
    def generate_policy_parameters(shares: int,
                                   payment_periods: int,
                                   value: int = None,
                                   rate: int = None) -> dict:

        # Check for negative inputs
        if sum(True for i in (shares, payment_periods, value, rate) if i is not None and i < 0) > 0:
            raise BlockchainPolicy.InvalidPolicyValue(f"Negative policy parameters are not allowed. Be positive.")

        # Check for policy params
        if not (bool(value) ^ bool(rate)):
            if not (value == 0 or rate == 0):  # Support a min fee rate of 0
                raise BlockchainPolicy.InvalidPolicyValue(f"Either 'value' or 'rate'  must be provided for policy. "
                                                          f"Got value: {value} and rate: {rate}")

        if value is None:
            value = rate * payment_periods * shares

        else:
            value_per_node = value // shares
            if value_per_node * shares != value:
                raise BlockchainPolicy.InvalidPolicyValue(f"Policy value of ({value} wei) cannot be"
                                                          f" divided by N ({shares}) without a remainder.")

            rate = value_per_node // payment_periods
            if rate * payment_periods != value_per_node:
                raise BlockchainPolicy.InvalidPolicyValue(f"Policy value of ({value_per_node} wei) per node "
                                                          f"cannot be divided by duration ({payment_periods} periods)"
                                                          f" without a remainder.")

        params = dict(rate=rate, value=value)
        return params

    def _make_reservoir(self, handpicked_addresses):
        staker_reservoir = make_decentralized_staker_reservoir(staking_agent=self.publisher.staking_agent,
                                                               duration_periods=self.payment_periods,
                                                               include_addresses=handpicked_addresses)
        return staker_reservoir

    def _publish_to_blockchain(self, ursulas) -> dict:

        addresses = [ursula.checksum_address for ursula in ursulas]

        # Transact  # TODO: Move this logic to BlockchainPolicyActor
        receipt = self.publisher.policy_agent.create_policy(
            policy_id=bytes(self.hrac),  # bytes16 _policyID
            transacting_power=self.publisher.transacting_power,
            value=self.value,
            end_timestamp=self.expiration.epoch,  # uint16 _numberOfPeriods
            node_addresses=addresses  # address[] memory _nodes
        )

        # Capture Response
        return receipt['transactionHash']

    def _make_enactment_payload(self, kfrag) -> bytes:
        return bytes(self.hrac) + bytes(kfrag)

    def _enact_arrangements(self, arrangements: Dict['Ursula', Arrangement]) -> None:
        self._publish_to_blockchain(ursulas=list(arrangements))


class EnactedPolicy:

    def __init__(self,
                 hrac: HRAC,
                 label: bytes,
                 public_key: PublicKey,
                 threshold: int,
                 treasure_map: 'EncryptedTreasureMap',
                 revocation_kit: RevocationKit,
                 publisher_verifying_key: PublicKey):

        self.hrac = hrac
        self.label = label
        self.public_key = public_key
        self.treasure_map = treasure_map
        self.revocation_kit = revocation_kit
        self.threshold = threshold
        self.shares = len(self.revocation_kit)
        self.publisher_verifying_key = publisher_verifying_key
