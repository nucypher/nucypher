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


import datetime
from collections import OrderedDict
from queue import Queue, Empty
from typing import Callable, Tuple, Sequence, Set, Optional, Iterable, List, Dict, Type

import math
import maya
import random
import time
from abc import ABC, abstractmethod
from bytestring_splitter import BytestringSplitter, VariableLengthBytestring
from constant_sorrow.constants import NOT_SIGNED
from eth_typing.evm import ChecksumAddress
from hexbytes import HexBytes
from twisted._threads import AlreadyQuit
from twisted.internet import reactor
from twisted.internet.defer import ensureDeferred, Deferred
from twisted.python.threadpool import ThreadPool
from umbral.keys import UmbralPublicKey
from umbral.kfrags import KFrag

from nucypher.blockchain.eth.actors import BlockchainPolicyAuthor
from nucypher.blockchain.eth.agents import PolicyManagerAgent, StakersReservoir, StakingEscrowAgent
from nucypher.characters.lawful import Alice, Ursula
from nucypher.crypto.api import keccak_digest, secure_random
from nucypher.crypto.constants import HRAC_LENGTH, PUBLIC_KEY_LENGTH
from nucypher.crypto.kits import RevocationKit
from nucypher.crypto.powers import DecryptingPower, SigningPower, TransactingPower
from nucypher.crypto.utils import construct_policy_id
from nucypher.network.exceptions import NodeSeemsToBeDown
from nucypher.network.middleware import RestMiddleware
from nucypher.utilities.logging import Logger


class Arrangement:
    """
    A contract between Alice and a single Ursula.
    """
    ID_LENGTH = 32

    splitter = BytestringSplitter((UmbralPublicKey, PUBLIC_KEY_LENGTH),  # alive_verifying_key
                                  (bytes, ID_LENGTH),  # arrangement_id
                                  (bytes, VariableLengthBytestring))  # expiration

    @classmethod
    def from_alice(cls, alice: Alice, expiration: maya.MayaDT) -> 'Arrangement':
        arrangement_id = secure_random(cls.ID_LENGTH)
        alice_verifying_key = alice.stamp.as_umbral_pubkey()
        return cls(alice_verifying_key, expiration, arrangement_id)

    def __init__(self,
                 alice_verifying_key: UmbralPublicKey,
                 expiration: maya.MayaDT,
                 arrangement_id: bytes,
                 ) -> None:
        if len(arrangement_id) != self.ID_LENGTH:
            raise ValueError(f"Arrangement ID must be of length {self.ID_LENGTH}.")
        self.id = arrangement_id
        self.expiration = expiration
        self.alice_verifying_key = alice_verifying_key

    def __bytes__(self):
        return bytes(self.alice_verifying_key) + self.id + bytes(VariableLengthBytestring(self.expiration.iso8601().encode()))

    @classmethod
    def from_bytes(cls, arrangement_as_bytes: bytes) -> 'Arrangement':
        alice_verifying_key, arrangement_id, expiration_bytes = cls.splitter(arrangement_as_bytes)
        expiration = maya.MayaDT.from_iso8601(iso8601_string=expiration_bytes.decode())
        return cls(alice_verifying_key=alice_verifying_key, arrangement_id=arrangement_id, expiration=expiration)

    def __repr__(self):
        return f"Arrangement(client_key={self.alice_verifying_key})"


class NodeEngagementMutex:
    """
    TODO: Does this belong on middleware?

    TODO: There are a couple of ways this can break.  If one fo the jobs hangs, the whole thing will hang.  Also,
       if there are fewer successfully completed than percent_to_complete_before_release, the partial queue will never
       release.

    TODO: Make registry per... I guess Policy?  It's weird to be able to accidentally enact again.
    """
    log = Logger("Policy")

    def __init__(self,
                 callable_to_engage,  # TODO: typing.Protocol
                 nodes,
                 network_middleware,
                 percent_to_complete_before_release=5,
                 note=None,
                 threadpool_size=120,
                 timeout=20,
                 *args,
                 **kwargs):
        self.f = callable_to_engage
        self.nodes = nodes
        self.network_middleware = network_middleware
        self.args = args
        self.kwargs = kwargs

        self.completed = {}
        self.failed = {}

        self._started = False
        self._finished = False
        self.timeout = timeout

        self.percent_to_complete_before_release = percent_to_complete_before_release
        self._partial_queue = Queue()
        self._completion_queue = Queue()
        self._block_until_this_many_are_complete = math.ceil(
            len(nodes) * self.percent_to_complete_before_release / 100)
        self.nodes_contacted_during_partial_block = False
        self.when_complete = Deferred()  # TODO: Allow cancelling via KB Interrupt or some other way?

        if note is None:
            self._repr = f"{callable_to_engage} to {len(nodes)} nodes"
        else:
            self._repr = f"{note}: {callable_to_engage} to {len(nodes)} nodes"

        self._threadpool = ThreadPool(minthreads=threadpool_size, maxthreads=threadpool_size, name=self._repr)
        self.log.info(f"NEM spinning up {self._threadpool}")
        self._threadpool.callInThread(self._bail_on_timeout)

    def __repr__(self):
        return self._repr

    def _bail_on_timeout(self):
        while True:
            if self.when_complete.called:
                return
            duration = datetime.datetime.now() - self._started
            if duration.seconds >= self.timeout:
                try:
                    self._threadpool.stop()
                except AlreadyQuit:
                    raise RuntimeError("Is there a race condition here?  If this line is being hit, it's a bug.")
                raise RuntimeError(f"Timed out.  Nodes completed: {self.completed}")
            time.sleep(.5)

    def block_until_success_is_reasonably_likely(self):
        """
        https://www.youtube.com/watch?v=OkSLswPSq2o
        """
        if len(self.completed) < self._block_until_this_many_are_complete:
            try:
                completed_for_reasonable_likelihood_of_success = self._partial_queue.get(timeout=self.timeout) # TODO: Shorter timeout here?
            except Empty:
                raise RuntimeError(f"Timed out.  Nodes completed: {self.completed}")
            self.log.debug(f"{len(self.completed)} nodes were contacted while blocking for a little while.")
            return completed_for_reasonable_likelihood_of_success
        else:
            return self.completed


    def block_until_complete(self):
        if self.total_disposed() < len(self.nodes):
            try:
                _ = self._completion_queue.get(timeout=self.timeout)  # Interesting opportuntiy to pass some data, like the list of contacted nodes above.
            except Empty:
                raise RuntimeError(f"Timed out.  Nodes completed: {self.completed}")
        if not reactor.running and not self._threadpool.joined:
            # If the reactor isn't running, the user *must* call this, because this is where we stop.
            self._threadpool.stop()

    def _handle_success(self, response, node):
        if response.status_code == 201:
            self.completed[node] = response
        else:
            assert False  # TODO: What happens if this is a 300 or 400 level response?  (A 500 response will propagate as an error and be handled in the errback chain.)
        if self.nodes_contacted_during_partial_block:
            self._consider_finalizing()
        else:
            if len(self.completed) >= self._block_until_this_many_are_complete:
                contacted = tuple(self.completed.keys())
                self.nodes_contacted_during_partial_block = contacted
                self.log.debug(f"Blocked for a little while, completed {contacted} nodes")
                self._partial_queue.put(contacted)
        return response

    def _handle_error(self, failure, node):
        self.failed[node] = failure  # TODO: Add a failfast mode?
        self._consider_finalizing()
        self.log.warn(f"{node} failed: {failure}")

    def total_disposed(self):
        return len(self.completed) + len(self.failed)

    def _consider_finalizing(self):
        if not self._finished:
            if self.total_disposed() == len(self.nodes):
                # TODO: Consider whether this can possibly hang.
                self._finished = True
                if reactor.running:
                    reactor.callInThread(self._threadpool.stop)
                self._completion_queue.put(self.completed)
                self.when_complete.callback(self.completed)
                self.log.info(f"{self} finished.")
        else:
            raise RuntimeError("Already finished.")

    def _engage_node(self, node):
        maybe_coro = self.f(node, network_middleware=self.network_middleware, *self.args, **self.kwargs)

        d = ensureDeferred(maybe_coro)
        d.addCallback(self._handle_success, node)
        d.addErrback(self._handle_error, node)
        return d

    def start(self):
        if self._started:
            raise RuntimeError("Already started.")
        self._started = datetime.datetime.now()
        self.log.info(f"NEM Starting {self._threadpool}")
        for node in self.nodes:
             self._threadpool.callInThread(self._engage_node, node)
        self._threadpool.start()


class MergedReservoir:
    """
    A reservoir made of a list of addresses and a StakersReservoir.
    Draws the values from the list first, then from StakersReservoir,
    then returns None on subsequent calls.
    """

    def __init__(self, values: Iterable, reservoir: StakersReservoir):
        self.values = list(values)
        self.reservoir = reservoir

    def __call__(self) -> Optional[ChecksumAddress]:
        if self.values:
            return self.values.pop(0)
        elif len(self.reservoir) > 0:
            return self.reservoir.draw(1)[0]
        else:
            return None


class PrefetchStrategy:
    """
    Encapsulates the batch draw strategy from a reservoir.
    Determines how many values to draw based on the number of values
    that have already led to successes.
    """

    def __init__(self, reservoir: MergedReservoir, need_successes: int):
        self.reservoir = reservoir
        self.need_successes = need_successes

    def __call__(self, successes: int) -> Optional[List[ChecksumAddress]]:
        batch = []
        for i in range(self.need_successes - successes):
            value = self.reservoir()
            if value is None:
                break
            batch.append(value)
        if not batch:
            return None
        return batch


def propose_arrangements(worker, value_factory, target_successes, timeout):
    """
    A temporary function that calls workers sequentially.
    To be replaced with a parallel solution.
    """

    successes = {}
    failures = {}
    start_time = maya.now()

    while True:

        value_batch = value_factory(len(successes))
        if value_batch is None:
            break

        for value in value_batch:
            try:
                result = worker(value)
                successes[value] = result
            except Exception as e:
                failures[value] = e

            if len(successes) == target_successes:
                break

            delta = maya.now() - start_time
            if delta.total_seconds() >= timeout:
                raise RuntimeError(f"Proposal stage timed out after {timeout} seconds; "
                                   f"need {target_successes - len(successes)} more.")

        if len(successes) == target_successes:
            break

    return successes, failures


class Policy(ABC):
    """
    An edict by Alice, arranged with n Ursulas, to perform re-encryption for a specific Bob.
    """

    POLICY_ID_LENGTH = 16

    log = Logger("Policy")

    class NotEnoughUrsulas(Exception):
        """
        Raised when a Policy has been used to generate Arrangements with Ursulas insufficient number
        such that we don't have enough KFrags to give to each Ursula.
        """

    class EnactmentError(Exception):
        """
        Raised if one or more Ursulas failed to enact the policy.
        """

    def __init__(self,
                 alice: Alice,
                 label: bytes,
                 expiration: maya.MayaDT,
                 bob: 'Bob',
                 kfrags: Sequence[KFrag],
                 public_key: UmbralPublicKey,
                 m: int,
                 ):

        """
        :param kfrags:  A list of KFrags to distribute per this Policy.
        :param label: The identity of the resource to which Bob is granted access.
        """

        self.m = m
        self.n = len(kfrags)
        self.alice = alice
        self.label = label
        self.bob = bob
        self.kfrags = kfrags
        self.public_key = public_key
        self.expiration = expiration

        self._id = construct_policy_id(self.label, bytes(self.bob.stamp))

        """
        # TODO: #180 - This attribute is hanging on for dear life.
        After 180 is closed, it can be completely deprecated.

        The "hashed resource authentication code".

        A hash of:
        * Alice's public key
        * Bob's public key
        * the label

        Alice and Bob have all the information they need to construct this.
        Ursula does not, so we share it with her.
        """
        self.hrac = keccak_digest(bytes(self.alice.stamp) + bytes(self.bob.stamp) + self.label)[:HRAC_LENGTH]

    def __repr__(self):
        return f"{self.__class__.__name__}:{self._id.hex()[:6]}"

    def _propose_arrangement(self,
                             address: ChecksumAddress,
                             network_middleware: RestMiddleware,
                             ) -> Tuple[Ursula, Arrangement]:
        """
        Attempt to propose an arrangement to the node with the given address.
        """

        if address not in self.alice.known_nodes:
            raise RuntimeError(f"{address} is not known")

        ursula = self.alice.known_nodes[address]
        arrangement = Arrangement.from_alice(alice=self.alice, expiration=self.expiration)

        self.log.debug(f"Proposing arrangement {arrangement} to {ursula}")
        negotiation_response = network_middleware.propose_arrangement(ursula, arrangement)
        status = negotiation_response.status_code

        if status == 200:
            self.log.debug(f"Arrangement accepted by {ursula}")
        else:
            message = f"Proposing arrangement to {ursula} failed with {status}"
            self.log.debug(message)
            raise RuntimeError(message)

        # We could just return the arrangement and get the Ursula object
        # from `known_nodes` later, but when we introduce slashing in FleetSensor,
        # the address can already disappear from `known_nodes` by that time.
        return (ursula, arrangement)

    @abstractmethod
    def _make_reservoir(self, handpicked_addresses: Sequence[ChecksumAddress]) -> MergedReservoir:
        """
        Builds a `MergedReservoir` to use for drawing addresses to send proposals to.
        """
        raise NotImplementedError

    def _make_arrangements(self,
                           network_middleware: RestMiddleware,
                           handpicked_ursulas: Optional[Iterable[Ursula]] = None,
                           discover_on_this_thread: bool = True,
                           timeout: int = 10,
                           ) -> Dict[Ursula, Arrangement]:
        """
        Pick some Ursula addresses and send them arrangement proposals.
        Returns a dictionary of Ursulas to Arrangements if it managed to get `n` responses.
        """

        if handpicked_ursulas is None:
            handpicked_ursulas = []
        handpicked_addresses = [ursula.checksum_address for ursula in handpicked_ursulas]

        reservoir = self._make_reservoir(handpicked_addresses)
        value_factory = PrefetchStrategy(reservoir, self.n)

        def worker(address):
            return self._propose_arrangement(address, network_middleware)

        self.alice.block_until_number_of_known_nodes_is(self.n, learn_on_this_thread=discover_on_this_thread, eager=True)

        arrangements, failures = propose_arrangements(worker=worker,
                                                      value_factory=value_factory,
                                                      target_successes=self.n,
                                                      timeout=timeout)

        accepted_arrangements = {ursula: arrangement for ursula, arrangement in arrangements.values()}

        accepted_addresses = ", ".join(ursula.checksum_address for ursula in accepted_arrangements)

        if len(arrangements) < self.n:

            rejected_proposals = "\n".join(f"{address}: {exception}" for address, exception in failures.items())

            self.log.debug(
                "Could not find enough Ursulas to accept proposals.\n"
                f"Accepted: {accepted_addresses}\n"
                f"Rejected:\n{rejected_proposals}")
            raise self._not_enough_ursulas_exception()
        else:
            self.log.debug(f"Finished proposing arrangements; accepted: {accepted_addresses}")

        return accepted_arrangements

    def _enact_arrangements(self,
                            network_middleware: RestMiddleware,
                            arrangements: Dict[Ursula, Arrangement],
                            publication_transaction: Optional[HexBytes] = None,
                            publish_treasure_map: bool = True,
                            ):
        """
        Attempts to distribute kfrags to Ursulas that accepted arrangements earlier.
        """

        statuses = {}
        for ursula, kfrag in zip(arrangements, self.kfrags):
            arrangement = arrangements[ursula]

            # TODO: seems like it would be enough to just encrypt this with Ursula's public key,
            # and not create a whole capsule.
            # Can't change for now since it's node protocol.
            payload = self._make_enactment_payload(publication_transaction, kfrag)
            message_kit, _signature = self.alice.encrypt_for(ursula, payload)

            try:
                # TODO: Concurrency
                response = network_middleware.enact_policy(ursula,
                                                           arrangement.id,
                                                           message_kit.to_bytes())
            except network_middleware.UnexpectedResponse as e:
                status = e.status
            else:
                status = response.status_code

            statuses[ursula.checksum_address] = status

        # TODO: Enable re-tries?

        if not all(status == 200 for status in statuses.values()):
            report = "\n".join(f"{address}: {status}" for address, status in statuses.items())
            self.log.debug(f"Policy enactment failed. Request statuses:\n{report}")

            # OK, let's check: if two or more Ursulas claimed we didn't pay,
            # we need to re-evaulate our situation here.
            number_of_claims_of_freeloading = sum(status == 402 for status in statuses.values())

            # TODO: a better exception here?
            if number_of_claims_of_freeloading > 2:
                raise self.alice.NotEnoughNodes

            # otherwise just raise a more generic error
            raise Policy.EnactmentError()

    def _make_treasure_map(self,
                           network_middleware: RestMiddleware,
                           arrangements: Dict[Ursula, Arrangement],
                           ) -> 'TreasureMap':
        """
        Creates a treasure map for given arrangements.
        """

        treasure_map = self._treasure_map_class(m=self.m)

        for ursula, arrangement in arrangements.items():
            treasure_map.add_arrangement(ursula, arrangement)

        treasure_map.prepare_for_publication(bob_encrypting_key=self.bob.public_keys(DecryptingPower),
                                             bob_verifying_key=self.bob.public_keys(SigningPower),
                                             alice_stamp=self.alice.stamp,
                                             label=self.label)

        return treasure_map

    def _make_publishing_mutex(self,
                               treasure_map: 'TreasureMap',
                               network_middleware: RestMiddleware,
                               ) -> NodeEngagementMutex:

        async def put_treasure_map_on_node(node, network_middleware):
            response = network_middleware.put_treasure_map_on_node(node=node,
                                                                   map_payload=bytes(treasure_map))
            return response

        # TODO (#2516): remove hardcoding of 8 nodes
        self.alice.block_until_number_of_known_nodes_is(8, timeout=2, learn_on_this_thread=True)
        target_nodes = self.bob.matching_nodes_among(self.alice.known_nodes)

        return NodeEngagementMutex(callable_to_engage=put_treasure_map_on_node,
                                   nodes=target_nodes,
                                   network_middleware=network_middleware)

    def enact(self,
              network_middleware: RestMiddleware,
              handpicked_ursulas: Optional[Iterable[Ursula]] = None,
              discover_on_this_thread: bool = True,
              publish_treasure_map: bool = True,
              ) -> 'EnactedPolicy':
        """
        Attempts to enact the policy, returns an `EnactedPolicy` object on success.
        """

        arrangements = self._make_arrangements(network_middleware=network_middleware,
                                               handpicked_ursulas=handpicked_ursulas,
                                               discover_on_this_thread=discover_on_this_thread)

        self._enact_arrangements(network_middleware=network_middleware,
                                 arrangements=arrangements,
                                 publish_treasure_map=publish_treasure_map)

        treasure_map = self._make_treasure_map(network_middleware=network_middleware,
                                               arrangements=arrangements)
        publishing_mutex = self._make_publishing_mutex(treasure_map=treasure_map,
                                                       network_middleware=network_middleware)
        revocation_kit = RevocationKit(treasure_map, self.alice.stamp)

        enacted_policy = EnactedPolicy(self._id,
                                       self.hrac,
                                       self.label,
                                       self.public_key,
                                       treasure_map,
                                       publishing_mutex,
                                       revocation_kit,
                                       self.alice.stamp)

        if publish_treasure_map is True:
            enacted_policy.publish_treasure_map()

        return enacted_policy

    @abstractmethod
    def _not_enough_ursulas_exception(self) -> Type[Exception]:
        """
        Returns an exception to raise when there were not enough Ursulas
        to distribute arrangements to.
        """
        raise NotImplementedError

    @abstractmethod
    def _make_enactment_payload(self, publication_transaction: Optional[HexBytes], kfrag: KFrag) -> bytes:
        """
        Serializes a given kfrag and policy publication transaction to send to Ursula.
        """
        raise NotImplementedError


class FederatedPolicy(Policy):

    from nucypher.policy.collections import TreasureMap as _treasure_map_class  # TODO: Circular Import

    def _not_enough_ursulas_exception(self):
        return Policy.NotEnoughUrsulas

    def _make_reservoir(self, handpicked_addresses):
        addresses = {
            ursula.checksum_address: 1 for ursula in self.alice.known_nodes
            if ursula.checksum_address not in handpicked_addresses}

        return MergedReservoir(handpicked_addresses, StakersReservoir(addresses))

    def _make_enactment_payload(self, publication_transaction, kfrag):
        assert publication_transaction is None # sanity check; should not ever be hit
        return bytes(kfrag)


class BlockchainPolicy(Policy):
    """
    A collection of n Arrangements representing a single Policy
    """

    from nucypher.policy.collections import SignedTreasureMap as _treasure_map_class  # TODO: Circular Import

    class InvalidPolicyValue(ValueError):
        pass

    class NotEnoughBlockchainUrsulas(Policy.NotEnoughUrsulas):
        pass

    def __init__(self,
                 value: int,
                 rate: int,
                 duration_periods: int,
                 *args,
                 **kwargs,
                 ):

        super().__init__(*args, **kwargs)

        self.duration_periods = duration_periods
        self.value = value
        self.rate = rate

        self._validate_fee_value()

    def _not_enough_ursulas_exception(self):
        return BlockchainPolicy.NotEnoughBlockchainUrsulas

    def _validate_fee_value(self) -> None:
        rate_per_period = self.value // self.n // self.duration_periods  # wei
        recalculated_value = self.duration_periods * rate_per_period * self.n
        if recalculated_value != self.value:
            raise ValueError(f"Invalid policy value calculation - "
                             f"{self.value} can't be divided into {self.n} staker payments per period "
                             f"for {self.duration_periods} periods without a remainder")

    @staticmethod
    def generate_policy_parameters(n: int,
                                   duration_periods: int,
                                   value: int = None,
                                   rate: int = None) -> dict:

        # Check for negative inputs
        if sum(True for i in (n, duration_periods, value, rate) if i is not None and i < 0) > 0:
            raise BlockchainPolicy.InvalidPolicyValue(f"Negative policy parameters are not allowed. Be positive.")

        # Check for policy params
        if not bool(value) ^ bool(rate):
            # TODO: Review this suggestion
            raise BlockchainPolicy.InvalidPolicyValue(f"Either 'value' or 'rate'  must be provided for policy.")

        if not value:
            value = rate * duration_periods * n

        else:
            value_per_node = value // n
            if value_per_node * n != value:
                raise BlockchainPolicy.InvalidPolicyValue(f"Policy value of ({value} wei) cannot be"
                                                          f" divided by N ({n}) without a remainder.")

            rate = value_per_node // duration_periods
            if rate * duration_periods != value_per_node:
                raise BlockchainPolicy.InvalidPolicyValue(f"Policy value of ({value_per_node} wei) per node "
                                                          f"cannot be divided by duration ({duration_periods} periods)"
                                                          f" without a remainder.")

        params = dict(rate=rate, value=value)
        return params

    def _make_reservoir(self, handpicked_addresses):
        try:
            reservoir = self.alice.get_stakers_reservoir(duration=self.duration_periods,
                                                         without=handpicked_addresses)
        except StakingEscrowAgent.NotEnoughStakers:
            # TODO: do that in `get_stakers_reservoir()`?
            reservoir = StakersReservoir({})

        return MergedReservoir(handpicked_addresses, reservoir)

    def _publish_to_blockchain(self, ursulas) -> dict:

        addresses = [ursula.checksum_address for ursula in ursulas]

        # Transact  # TODO: Move this logic to BlockchainPolicyActor
        receipt = self.alice.policy_agent.create_policy(
            policy_id=self.hrac,  # bytes16 _policyID
            author_address=self.alice.checksum_address,
            value=self.value,
            end_timestamp=self.expiration.epoch,  # uint16 _numberOfPeriods
            node_addresses=addresses  # address[] memory _nodes
        )

        # Capture Response
        return receipt['transactionHash']

    def _make_enactment_payload(self, publication_transaction, kfrag):
        return bytes(publication_transaction) + bytes(kfrag)

    def _enact_arrangements(self,
                            network_middleware,
                            arrangements,
                            publish_treasure_map=True) -> NodeEngagementMutex:
        transaction = self._publish_to_blockchain(list(arrangements))
        return super()._enact_arrangements(network_middleware=network_middleware,
                                           arrangements=arrangements,
                                           publish_treasure_map=publish_treasure_map,
                                           publication_transaction=transaction)

    def _make_treasure_map(self,
                           network_middleware: RestMiddleware,
                           arrangements: Dict[Ursula, Arrangement],
                           ) -> 'TreasureMap':

        treasure_map = super()._make_treasure_map(network_middleware, arrangements)
        transacting_power = self.alice._crypto_power.power_ups(TransactingPower)
        treasure_map.include_blockchain_signature(transacting_power.sign_message)
        return treasure_map


class EnactedPolicy:

    def __init__(self,
                 id: bytes,
                 hrac: bytes,
                 label: bytes,
                 public_key: UmbralPublicKey,
                 treasure_map: 'TreasureMap',
                 publishing_mutex: NodeEngagementMutex,
                 revocation_kit: RevocationKit,
                 alice_verifying_key: UmbralPublicKey,
                 ):

        self.id = id # TODO: is it even used anywhere?
        self.hrac = hrac
        self.label = label
        self.public_key = public_key
        self.treasure_map = treasure_map
        self.publishing_mutex = publishing_mutex
        self.revocation_kit = revocation_kit
        self.n = len(self.treasure_map.destinations)
        self.alice_verifying_key = alice_verifying_key

    def publish_treasure_map(self):
        self.publishing_mutex.start()
