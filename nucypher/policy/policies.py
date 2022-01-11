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
from typing import Sequence, Optional, Iterable, List

import maya
from eth_typing.evm import ChecksumAddress
from hexbytes import HexBytes
from nucypher_core import HRAC, TreasureMap
from nucypher_core.umbral import PublicKey, VerifiedKeyFrag

from nucypher.blockchain.eth.agents import ContractAgency, StakingEscrowAgent
from nucypher.blockchain.eth.utils import calculate_period_duration
from nucypher.crypto.powers import DecryptingPower
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
        Raised when a Policy cannot be generated due an an insufficient
        number of available qualified network nodes.
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
        """Raised when Bob is not authorized to request re-encryption from Ursula.."""

    class Revoked(Unauthorized):
        """Raised when a policy is revoked has been revoked access"""

    def __init__(self,
                 publisher: 'Alice',
                 label: bytes,
                 bob: 'Bob',
                 kfrags: Sequence[VerifiedKeyFrag],
                 public_key: PublicKey,
                 threshold: int,
                 expiration: maya.MayaDT,
                 commencement: Optional[maya.MayaDT] = None
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
        self.commencement = commencement
        self.hrac = HRAC(publisher_verifying_key=self.publisher.stamp.as_umbral_pubkey(),
                         bob_verifying_key=self.bob.stamp.as_umbral_pubkey(),
                         label=self.label)

    def __repr__(self):
        return f"{self.__class__.__name__}:{bytes(self.hrac).hex()[:6]}"

    @abstractmethod
    def _make_reservoir(self, handpicked_addresses: Sequence[ChecksumAddress]) -> MergedReservoir:
        """Builds a `MergedReservoir` to use for drawing addresses to send proposals to."""
        raise NotImplementedError

    @abstractmethod
    def _publish(self, ursulas: List['Ursula']) -> None:
        raise NotImplementedError

    def _ping_node(self, address: ChecksumAddress, network_middleware: RestMiddleware) -> 'Ursula':
        # Handles edge case when provided address is not a known peer.
        if address not in self.publisher.known_nodes:
            raise RuntimeError(f"{address} is not a known peer")

        ursula = self.publisher.known_nodes[address]
        response = network_middleware.ping(node=ursula)
        status_code = response.status_code

        if status_code == 200:
            return ursula
        else:
            raise RuntimeError(f"{ursula} is not available for selection ({status_code}).")

    def _sample(self,
                network_middleware: RestMiddleware,
                ursulas: Optional[Iterable['Ursula']] = None,
                timeout: int = 10,
                ) -> List['Ursula']:
        """Send concurrent requests to the /ping HTTP endpoint of nodes drawn from the reservoir."""

        ursulas = ursulas or []
        handpicked_addresses = [ChecksumAddress(ursula.checksum_address) for ursula in ursulas]

        self.publisher.block_until_number_of_known_nodes_is(self.shares, learn_on_this_thread=True, eager=True)
        reservoir = self._make_reservoir(handpicked_addresses)
        value_factory = PrefetchStrategy(reservoir, self.shares)

        def worker(address) -> 'Ursula':
            return self._ping_node(address, network_middleware)

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
            # It's possible to raise some other exceptions here but we will use the logic below.
            successes = worker_pool.get_successes()
        finally:
            worker_pool.cancel()
            worker_pool.join()
        failures = worker_pool.get_failures()

        accepted_addresses = ", ".join(ursula.checksum_address for ursula in successes.values())
        if len(successes) < self.shares:
            rejections = "\n".join(f"{address}: {value}" for address, (type_, value, traceback) in failures.items())
            message = "Failed to contact enough sampled nodes.\n"\
                      f"Selected:\n{accepted_addresses}\n" \
                      f"Unavailable:\n{rejections}"
            self.log.debug(message)
            raise self.NotEnoughUrsulas(message)

        self.log.debug(f"Selected nodes for policy: {accepted_addresses}")
        ursulas = list(successes.values())
        return ursulas

    def enact(self, network_middleware: RestMiddleware, ursulas: Optional[Iterable['Ursula']] = None) -> 'EnactedPolicy':
        """Attempts to enact the policy, returns an `EnactedPolicy` object on success."""

        ursulas = self._sample(network_middleware=network_middleware, ursulas=ursulas)
        self._publish(ursulas=ursulas)

        assigned_kfrags = {
            ursula.canonical_address: (ursula.public_keys(DecryptingPower), vkfrag)
            for ursula, vkfrag in zip(ursulas, self.kfrags)
        }

        treasure_map = TreasureMap(signer=self.publisher.stamp.as_umbral_signer(),
                                   hrac=self.hrac,
                                   policy_encrypting_key=self.public_key,
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


class FederatedPolicy(Policy):

    def _publish(self, ursulas: List['Ursula']) -> None:
        """Hook to perform publication operations for federated policies."""
        pass

    def _make_reservoir(self, handpicked_addresses):
        """Returns a federated node reservoir for creating a federated policy."""
        return make_federated_staker_reservoir(known_nodes=self.publisher.known_nodes,
                                               include_addresses=handpicked_addresses)


class BlockchainPolicy(Policy):

    class InvalidPolicyValue(ValueError):
        pass

    def __init__(self,
                 value: int,
                 rate: int,
                 duration: int,
                 *args,
                 **kwargs):
        super().__init__(*args, **kwargs)
        self.duration = duration
        self.value = value
        self.rate = rate

        # This part is a bit hacky bit it gets the job done.
        # This allows payment logic to be decoupled from instances
        # of this object. A future improvement may remove this class entirely
        # in favor of a more simple PolicyInfo.
        self.staking_agent = ContractAgency.get_agent(StakingEscrowAgent, registry=self.publisher.registry)
        self.publisher.payment_method.validate_rate(
            shares=self.shares,
            value=value,
            duration=duration
        )
        self.addresses = None

    def _publish(self, ursulas: List['Ursula']) -> HexBytes:
        self.addresses = [ursula.checksum_address for ursula in ursulas]
        txid = self.publisher.payment_method.pay(policy=self)
        return txid

    def _make_reservoir(self, handpicked_addresses):
        """Returns a reservoir of staking nodes to create a decentralized policy."""

        # TODO: Dissolve this shim to provide compatibility between SubscriptionManager and StakingEscrow sampling
        # Handles the duration unit difference between PolicyManager (periods) and SubscriptionManager (seconds)
        # this can be further abstracted away (into payments?) or removed when StakingEscrow periods are fully deprecated.
        from nucypher.policy.payment import SubscriptionManagerPayment
        duration = self.duration
        if isinstance(self.publisher.payment_method, SubscriptionManagerPayment):
            economics = self.publisher.payment_method.economics
            duration = calculate_period_duration(future_time=self.expiration,
                                                 seconds_per_period=economics.seconds_per_period)

        staker_reservoir = make_decentralized_staker_reservoir(staking_agent=self.staking_agent,
                                                               duration_periods=duration,
                                                               include_addresses=handpicked_addresses)
        return staker_reservoir


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
