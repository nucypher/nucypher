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
from typing import Callable, Tuple
from typing import Generator, Set, Optional

import math
import maya
import random
import time
from abc import ABC, abstractmethod
from bytestring_splitter import BytestringSplitter, VariableLengthBytestring
from constant_sorrow.constants import NOT_SIGNED, UNKNOWN_KFRAG
from twisted._threads import AlreadyQuit
from twisted.internet import reactor
from twisted.internet.defer import ensureDeferred, Deferred
from twisted.python.threadpool import ThreadPool
from umbral.keys import UmbralPublicKey
from umbral.kfrags import KFrag

from nucypher.blockchain.eth.actors import BlockchainPolicyAuthor
from nucypher.blockchain.eth.agents import PolicyManagerAgent
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


class Policy(ABC):
    """
    An edict by Alice, arranged with n Ursulas, to perform re-encryption for a specific Bob
    for a specific path.

    Once Alice is ready to enact a Policy, she generates KFrags, which become part of the Policy.

    Each Ursula is offered a Arrangement (see above) for a given Policy by Alice.

    Once Alice has secured agreement with n Ursulas to enact a Policy, she sends each a KFrag,
    and generates a TreasureMap for the Policy, recording which Ursulas got a KFrag.
    """

    POLICY_ID_LENGTH = 16
    _arrangement_class = NotImplemented

    log = Logger("Policy")

    class Rejected(RuntimeError):
        """Too many Ursulas rejected"""

    def __init__(self,
                 alice: Alice,
                 label: bytes,
                 expiration: maya.MayaDT,
                 bob: 'Bob' = None,
                 kfrags: Tuple[KFrag, ...] = (UNKNOWN_KFRAG,),
                 public_key=None,
                 m: int = None,
                 alice_signature=NOT_SIGNED) -> None:

        """
        :param kfrags:  A list of KFrags to distribute per this Policy.
        :param label: The identity of the resource to which Bob is granted access.
        """
        self.alice = alice
        self.label = label
        self.bob = bob
        self.kfrags = kfrags
        self.public_key = public_key
        self._id = construct_policy_id(self.label, bytes(self.bob.stamp))
        self.treasure_map = self._treasure_map_class(m=m)
        self.expiration = expiration

        self._accepted_arrangements = {}       # type: Dict[Ursula, Arrangement]
        self._rejected_arrangements = set()    # type: Set[Arrangement]
        self._spare_candidates = set()         # type: Set[Ursula]

        self._enacted_arrangements = OrderedDict()
        self._published_arrangements = OrderedDict()

        self.alice_signature = alice_signature  # TODO: This is unused / To Be Implemented?

        self.publishing_mutex = None

    class MoreKFragsThanArrangements(TypeError):
        """
        Raised when a Policy has been used to generate Arrangements with Ursulas insufficient number
        such that we don't have enough KFrags to give to each Ursula.
        """

    @property
    def n(self) -> int:
        return len(self.kfrags)

    @property
    def id(self) -> bytes:
        return self._id

    def __repr__(self):
        return f"{self.__class__.__name__}:{self.id.hex()[:6]}"

    @property
    def accepted_ursulas(self) -> Set[Ursula]:
        return set(self._accepted_arrangements)

    def hrac(self) -> bytes:
        """
        # TODO: #180 - This function is hanging on for dear life.  After 180 is closed, it can be completely deprecated.

        The "hashed resource authentication code".

        A hash of:
        * Alice's public key
        * Bob's public key
        * the label

        Alice and Bob have all the information they need to construct this.
        Ursula does not, so we share it with her.
        """
        return keccak_digest(bytes(self.alice.stamp) + bytes(self.bob.stamp) + self.label)[:HRAC_LENGTH]

    async def put_treasure_map_on_node(self, node, network_middleware):
        response = network_middleware.put_treasure_map_on_node(
            node=node,
            map_payload=bytes(self.treasure_map))
        return response

    def publish_treasure_map(self, network_middleware: RestMiddleware,
                             blockchain_signer: Callable = None) -> NodeEngagementMutex:
        self.treasure_map.prepare_for_publication(self.bob.public_keys(DecryptingPower),
                                                  self.bob.public_keys(SigningPower),
                                                  self.alice.stamp,
                                                  self.label)
        if blockchain_signer is not None:
            self.treasure_map.include_blockchain_signature(blockchain_signer)

        self.alice.block_until_number_of_known_nodes_is(8, timeout=2, learn_on_this_thread=True)

        target_nodes = self.bob.matching_nodes_among(self.alice.known_nodes)
        self.publishing_mutex = NodeEngagementMutex(callable_to_engage=self.put_treasure_map_on_node,
                                                    nodes=target_nodes,
                                                    network_middleware=network_middleware)

        self.publishing_mutex.start()

    def make_enactment_payload(self, kfrag):
        return bytes(kfrag)

    def enact(self, network_middleware, publish_treasure_map=True) -> dict:
        """
        Assign kfrags to ursulas_on_network, and distribute them via REST,
        populating enacted_arrangements
        """
        if len(self._accepted_arrangements) < self.n:
            raise self.MoreKFragsThanArrangements("Not enough candidate arrangements. "
                                                  "Call make_arrangements to make more.")

        arrangement_statuses = []
        for ursula, kfrag in zip(self._accepted_arrangements, self.kfrags):
            arrangement = self._accepted_arrangements[ursula]
            # TODO: seems like it would be enough to just encrypt this with Ursula's public key,
            # and not create a whole capsule.
            # Can't change for now since it's node protocol.
            message_kit, _signature = self.alice.encrypt_for(ursula, self.make_enactment_payload(kfrag))

            try:
                # TODO: Concurrency
                response = network_middleware.enact_policy(ursula,
                                                           arrangement.id,
                                                           message_kit.to_bytes())
            except network_middleware.UnexpectedResponse as e:
                arrangement_status = e.status
            else:
                arrangement_status = response.status_code

            arrangement_statuses.append(arrangement_status)

            # TODO: Handle problem here - if the arrangement is bad, deal with it.
            self.treasure_map.add_arrangement(ursula, arrangement)
            self._enacted_arrangements[ursula] = kfrag

        else:
            # OK, let's check: if two or more Ursulas claimed we didn't pay,
            # we need to re-evaulate our situation here.
            number_of_claims_of_freeloading = sum(status == 402 for status in arrangement_statuses)

            if number_of_claims_of_freeloading > 2:
                raise self.alice.NotEnoughNodes  # TODO: Clean this up and enable re-tries.

            self.treasure_map.check_for_sufficient_destinations()

            # TODO: Leave a note to try any failures later.
            pass

            # ...After *all* the arrangements are enacted
            # Create Alice's revocation kit
            self.revocation_kit = RevocationKit(self, self.alice.stamp)
            self.alice.add_active_policy(self)

            if publish_treasure_map is True:
                return self.publish_treasure_map(network_middleware=network_middleware)  # TODO: blockchain_signer?

    def propose_arrangement(self, ursula, network_middleware, arrangement) -> bool:
        negotiation_response = network_middleware.propose_arrangement(node=ursula, arrangement=arrangement)

        # TODO: check out the response: need to assess the result and see if we're actually good to go.
        arrangement_is_accepted = negotiation_response.status_code == 200

        return arrangement_is_accepted

    def make_arrangements(self,
                          network_middleware: RestMiddleware,
                          handpicked_ursulas: Optional[Set[Ursula]] = None,
                          discover_on_this_thread: bool = True,
                          *args, **kwargs,
                          ) -> None:

        sampled_ursulas = self.sample(handpicked_ursulas=handpicked_ursulas,
                                      discover_on_this_thread=discover_on_this_thread)

        if len(sampled_ursulas) < self.n:
            raise self.MoreKFragsThanArrangements(
                "To make a Policy in federated mode, you need to designate *all* '  \
                 the Ursulas you need (in this case, {}); there's no other way to ' \
                 know which nodes to use.  Either pass them here or when you make ' \
                 the Policy.".format(self.n))

        # TODO: One of these layers needs to add concurrency.
        self._propose_arrangements(network_middleware=network_middleware,
                                   candidate_ursulas=sampled_ursulas,
                                   *args, **kwargs)

        if len(self._accepted_arrangements) < self.n:
            formatted_offenders = '\n'.join(f'{u.checksum_address}@{u.rest_url()}' for u in sampled_ursulas)
            raise self.Rejected(f'Selected Ursulas rejected too many arrangements'
                                f'- only {len(self._accepted_arrangements)} of {self.n} accepted.\n'
                                f'Offending nodes: \n{formatted_offenders}\n')

    def make_arrangement(self):
        return Arrangement.from_alice(alice=self.alice, expiration=self.expiration)

    @abstractmethod
    def sample_essential(self, *args, **kwargs) -> Set[Ursula]:
        raise NotImplementedError

    def sample(self,
               handpicked_ursulas: Optional[Set[Ursula]] = None,
               discover_on_this_thread: bool = False,
               ) -> Set[Ursula]:
        selected_ursulas = set(handpicked_ursulas) if handpicked_ursulas else set()

        # Calculate the target sample quantity
        if self.n - len(selected_ursulas) > 0:
            sampled_ursulas = self.sample_essential(handpicked_ursulas=selected_ursulas,
                                                    discover_on_this_thread=discover_on_this_thread)
            selected_ursulas.update(sampled_ursulas)

        return selected_ursulas

    def _propose_arrangements(self,
                              network_middleware: RestMiddleware,
                              candidate_ursulas: Set[Ursula],
                              consider_everyone: bool = False,
                              *args,
                              **kwargs) -> None:

        for index, selected_ursula in enumerate(candidate_ursulas):
            arrangement = self.make_arrangement(*args, **kwargs)
            try:
                is_accepted = self.propose_arrangement(ursula=selected_ursula,
                                                       arrangement=arrangement,
                                                       network_middleware=network_middleware)

            except NodeSeemsToBeDown as e:  # TODO: #355 Also catch InvalidNode here?
                # This arrangement won't be added to the accepted bucket.
                # If too many nodes are down, it will fail in make_arrangements.
                # Also TODO: Prolly log this or something at this stage.
                continue

            else:
                # Bucket the arrangements
                if is_accepted:
                    self.log.debug(f"Arrangement accepted by {selected_ursula}")
                    self._accepted_arrangements[selected_ursula] = arrangement
                    accepted = len(self._accepted_arrangements)
                    if accepted == self.n and not consider_everyone:
                        try:
                            spares = set(list(candidate_ursulas)[index + 1::])
                            self._spare_candidates.update(spares)
                        except IndexError:
                            self._spare_candidates = set()
                        break
                else:
                    self.log.debug(f"Arrangement failed with {selected_ursula}")
                    self._rejected_arrangements.add(arrangement)


class FederatedPolicy(Policy):
    _arrangement_class = Arrangement
    from nucypher.policy.collections import TreasureMap as _treasure_map_class  # TODO: Circular Import

    def make_arrangements(self, *args, **kwargs) -> None:
        try:
            return super().make_arrangements(*args, **kwargs)
        except self.MoreKFragsThanArrangements:
            error = "To make a Policy in federated mode, you need to designate *all* '  \
                     the Ursulas you need (in this case, {}); there's no other way to ' \
                     know which nodes to use.  " \
                    "Pass them here as handpicked_ursulas.".format(self.n)
            raise self.MoreKFragsThanArrangements(error)  # TODO: NotEnoughUrsulas where in the exception tree is this?

    def sample_essential(self,
                         handpicked_ursulas: Set[Ursula],
                         discover_on_this_thread: bool = True) -> Set[Ursula]:

        self.alice.block_until_specific_nodes_are_known(set(ursula.checksum_address for ursula in handpicked_ursulas))
        self.alice.block_until_number_of_known_nodes_is(self.n, learn_on_this_thread=discover_on_this_thread)
        known_nodes = self.alice.known_nodes
        if handpicked_ursulas:
            # Prevent re-sampling of handpicked ursulas.
            known_nodes = set(known_nodes) - handpicked_ursulas
        sampled_ursulas = set(random.sample(k=self.n - len(handpicked_ursulas),
                                            population=list(known_nodes)))
        return sampled_ursulas


class BlockchainPolicy(Policy):
    """
    A collection of n BlockchainArrangements representing a single Policy
    """
    from nucypher.policy.collections import SignedTreasureMap as _treasure_map_class  # TODO: Circular Import

    class NoSuchPolicy(Exception):
        pass

    class InvalidPolicy(Exception):
        pass

    class InvalidPolicyValue(ValueError):
        pass

    class NotEnoughBlockchainUrsulas(Policy.MoreKFragsThanArrangements):
        pass

    def __init__(self,
                 alice: Alice,
                 value: int,
                 rate: int,
                 duration_periods: int,
                 expiration: maya.MayaDT,
                 *args, **kwargs):

        self.duration_periods = duration_periods
        self.expiration = expiration
        self.value = value
        self.rate = rate
        self.author = alice

        # Initial State
        self.publish_transaction = None
        self.is_published = False
        self.receipt = None

        super().__init__(alice=alice, expiration=expiration, *args, **kwargs)

        self.validate_fee_value()

    def validate_fee_value(self) -> None:
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

    def sample_essential(self,
                         handpicked_ursulas: Set[Ursula],
                         learner_timeout: int = 1,
                         timeout: int = 10,
                         discover_on_this_thread: bool = False) -> Set[Ursula]: # TODO #843: Make timeout configurable

        handpicked_addresses = [ursula.checksum_address for ursula in handpicked_ursulas]
        reservoir = self.alice.get_stakers_reservoir(duration=self.duration_periods,
                                                     without=handpicked_addresses)

        quantity_remaining = self.n - len(handpicked_ursulas)
        if len(reservoir) < quantity_remaining:
            error = f"Cannot create policy with {self.n} arrangements"
            raise self.NotEnoughBlockchainUrsulas(error)

        # Handpicked Ursulas are not necessarily known
        to_check = list(handpicked_ursulas) + reservoir.draw(quantity_remaining)
        checked = []

        # Sample stakers in a loop and feed them to the learner to check
        # until we have enough in `selected_ursulas`.

        start_time = maya.now()

        while True:

            # Check if the sampled addresses are already known.
            # If we're lucky, we won't have to wait for the learner iteration to finish.
            checked += [x for x in to_check if x in self.alice.known_nodes]
            to_check = [x for x in to_check if x not in self.alice.known_nodes]

            if len(checked) >= self.n:
                break

            # The number of new nodes to draw on each iteration.
            # The choice of this depends on how expensive it is to check a node for validity,
            # and how likely is it for a picked node to be offline.
            # We assume here that it is unlikely, and be conservative.
            drawing_step = self.n - len(checked)

            # Draw a little bit more nodes, if there are any
            to_check += reservoir.draw_at_most(drawing_step)

            delta = maya.now() - start_time
            if delta.total_seconds() >= timeout:
                still_checking = ', '.join(to_check)
                quantity_remaining = self.n - len(checked)
                raise RuntimeError(f"Timed out after {timeout} seconds; "
                                   f"need {quantity_remaining} more, still checking {still_checking}.")

            self.alice.block_until_specific_nodes_are_known(to_check,
                                                            learn_on_this_thread=discover_on_this_thread,
                                                            allow_missing=len(to_check),
                                                            timeout=learner_timeout)

        # We only need `n` nodes. Pick the first `n` ones,
        # since they were the first drawn, and hence have the priority.
        found_ursulas = [self.alice.known_nodes[address] for address in checked[:self.n]]

        # Randomize the output to avoid the largest stakers always being the first in the list
        system_random = random.SystemRandom()
        system_random.shuffle(found_ursulas) # inplace

        return set(found_ursulas)

    def publish_to_blockchain(self) -> dict:

        prearranged_ursulas = list(ursula.checksum_address for ursula in self._accepted_arrangements)

        # Transact  # TODO: Move this logic to BlockchainPolicyActor
        receipt = self.author.policy_agent.create_policy(
            policy_id=self.hrac(),  # bytes16 _policyID
            author_address=self.author.checksum_address,
            value=self.value,
            end_timestamp=self.expiration.epoch,  # uint16 _numberOfPeriods
            node_addresses=prearranged_ursulas  # address[] memory _nodes
        )

        # Capture Response
        self.receipt = receipt
        self.publish_transaction = receipt['transactionHash']
        self.is_published = True  # TODO: For real: TX / Swarm confirmations needed?

        return receipt

    def make_enactment_payload(self, kfrag):
        return bytes(self.publish_transaction) + super().make_enactment_payload(kfrag)

    def enact(self, network_middleware, publish_to_blockchain=True, publish_treasure_map=True) -> NodeEngagementMutex:
        """
        Assign kfrags to ursulas_on_network, and distribute them via REST,
        populating enacted_arrangements
        """
        if publish_to_blockchain is True:
            self.publish_to_blockchain()

        publisher = super().enact(network_middleware, publish_treasure_map=False)

        if publish_treasure_map is True:
            self.treasure_map.prepare_for_publication(bob_encrypting_key=self.bob.public_keys(DecryptingPower),
                                                      bob_verifying_key=self.bob.public_keys(SigningPower),
                                                      alice_stamp=self.alice.stamp,
                                                      label=self.label)
            # Sign the map.
            transacting_power = self.alice._crypto_power.power_ups(TransactingPower)
            publisher = self.publish_treasure_map(network_middleware=network_middleware,
                                                  blockchain_signer=transacting_power.sign_message)
        return publisher
