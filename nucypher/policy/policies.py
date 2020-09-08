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
import math
import time
import random
from abc import ABC, abstractmethod
from collections import OrderedDict, deque
from queue import Queue
from typing import Callable
from typing import Generator, List, Set

import maya
from twisted.internet import reactor
from twisted.internet.defer import ensureDeferred, Deferred
from twisted.python.threadpool import ThreadPool

from bytestring_splitter import BytestringSplitter, VariableLengthBytestring
from constant_sorrow.constants import NOT_SIGNED, UNKNOWN_KFRAG
from typing import Generator, List, Set, Optional
from umbral.keys import UmbralPublicKey
from umbral.kfrags import KFrag

from nucypher.blockchain.eth.actors import BlockchainPolicyAuthor
from nucypher.blockchain.eth.agents import PolicyManagerAgent, StakingEscrowAgent
from nucypher.characters.lawful import Alice, Ursula
from nucypher.crypto.api import keccak_digest, secure_random
from nucypher.crypto.constants import PUBLIC_KEY_LENGTH
from nucypher.crypto.kits import RevocationKit
from nucypher.crypto.powers import DecryptingPower, SigningPower, TransactingPower
from nucypher.crypto.utils import construct_policy_id
from nucypher.network.exceptions import NodeSeemsToBeDown
from nucypher.network.middleware import RestMiddleware
from nucypher.utilities.logging import Logger
from umbral.keys import UmbralPublicKey
from umbral.kfrags import KFrag


class Arrangement:
    """
    A Policy must be implemented by arrangements with n Ursulas.  This class tracks the status of that implementation.
    """
    federated = True
    ID_LENGTH = 32

    splitter = BytestringSplitter((UmbralPublicKey, PUBLIC_KEY_LENGTH),  # alice.stamp
                                  (bytes, ID_LENGTH),  # arrangement_ID
                                  (bytes, VariableLengthBytestring))  # expiration

    def __init__(self,
                 alice: Alice,
                 expiration: maya.MayaDT,
                 ursula: Ursula = None,
                 arrangement_id: bytes = None,
                 kfrag: KFrag = UNKNOWN_KFRAG
                 ) -> None:
        """
        :param value: Funds which will pay for the timeframe  of this Arrangement (not the actual re-encryptions);
                      a portion will be locked for each Ursula that accepts.
        :param expiration: The moment which Alice wants the Arrangement to end.

        Other params are hopefully self-evident.
        """
        if arrangement_id:
            if len(arrangement_id) != self.ID_LENGTH:
                raise ValueError(f"Arrangement ID must be of length {self.ID_LENGTH}.")
            self.id = arrangement_id
        else:
            self.id = secure_random(self.ID_LENGTH)
        self.expiration = expiration
        self.alice = alice
        self.status = None

        """
        These will normally not be set if Alice is drawing up this arrangement - she hasn't assigned a kfrag yet
        (because she doesn't know if this Arrangement will be accepted).  She doesn't have an Ursula, for the same reason.
        """
        self.kfrag = kfrag
        self.ursula = ursula

    def __bytes__(self):
        return bytes(self.alice.stamp) + self.id + bytes(VariableLengthBytestring(self.expiration.iso8601().encode()))

    @classmethod
    def from_bytes(cls, arrangement_as_bytes):
        alice_verifying_key, arrangement_id, expiration_bytes = cls.splitter(arrangement_as_bytes)
        expiration = maya.MayaDT.from_iso8601(iso8601_string=expiration_bytes.decode())
        alice = Alice.from_public_keys(verifying_key=alice_verifying_key)
        return cls(alice=alice, arrangement_id=arrangement_id, expiration=expiration)

    def encrypt_payload_for_ursula(self):
        """Craft an offer to send to Ursula."""
        # We don't need the signature separately.
        return self.alice.encrypt_for(self.ursula, self.payload())[0]

    def payload(self):
        return bytes(self.kfrag)

    @abstractmethod
    def revoke(self):
        """
        Revoke arrangement.
        """
        raise NotImplementedError


class BlockchainArrangement(Arrangement):
    """
    A relationship between Alice and a single Ursula as part of Blockchain Policy
    """
    federated = False

    class InvalidArrangement(Exception):
        pass

    def __init__(self,
                 alice: Alice,
                 ursula: Ursula,
                 rate: int,
                 expiration: maya.MayaDT,
                 duration_periods: int,
                 *args, **kwargs):
        super().__init__(alice=alice, ursula=ursula, expiration=expiration, *args, **kwargs)

        # The relationship exists between two addresses
        self.author = alice  # type: BlockchainPolicyAuthor
        self.policy_agent = alice.policy_agent  # type: PolicyManagerAgent
        self.staker = ursula  # type: Ursula

        # Arrangement rate and duration in periods
        self.rate = rate
        self.duration_periods = duration_periods

        # Status
        self.is_published = False
        self.publish_transaction = None
        self.is_revoked = False
        self.revoke_transaction = None

    def __repr__(self):
        class_name = self.__class__.__name__
        r = "{}(client={}, node={})"
        r = r.format(class_name, self.author, self.staker)
        return r

    def revoke(self) -> str:
        """Revoke this arrangement and return the transaction hash as hex."""
        # TODO: #1355 - Revoke arrangements only
        txhash = self.policy_agent.revoke_policy(self.id, author_address=self.author.checksum_address)
        self.revoke_transaction = txhash
        self.is_revoked = True
        return txhash

    def payload(self):
        partial_payload = super().payload()
        return bytes(self.publish_transaction) + partial_payload


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

    def __repr__(self):
        return self._repr

    def block_until_success_is_reasonably_likely(self):
        """
        https://www.youtube.com/watch?v=OkSLswPSq2o
        """
        if len(self.completed) < self._block_until_this_many_are_complete:
            completed_for_reasonable_likelihood_of_success = self._partial_queue.get()  # Interesting opportuntiy to pass some data, like the list of contacted nodes above.
            self.log.debug(f"{len(self.completed)} nodes were contacted while blocking for a little while.")
            return completed_for_reasonable_likelihood_of_success
        else:
            return self.completed

    def block_until_complete(self):
        if self.total_disposed() < len(self.nodes):
            _ = self._completion_queue.get()  # Interesting opportuntiy to pass some data, like the list of contacted nodes above.
        if not reactor.running and not self._threadpool.joined:
            # If the reactor isn't running, the user *must* call this, because this is where we stop.
            self._threadpool.stop()

    def _handle_success(self, response, node):
        if response.status_code == 202:
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
        self._started = True
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
                 alice,
                 label,
                 expiration: maya.MayaDT,
                 bob=None,
                 kfrags=(UNKNOWN_KFRAG,),
                 public_key=None,
                 m: int = None,
                 alice_signature=NOT_SIGNED) -> None:

        """
        :param kfrags:  A list of KFrags to distribute per this Policy.
        :param label: The identity of the resource to which Bob is granted access.
        """
        self.alice = alice  # type: Alice
        self.label = label  # type: bytes
        self.bob = bob  # type: Bob
        self.kfrags = kfrags  # type: List[KFrag]
        self.public_key = public_key
        self._id = construct_policy_id(self.label, bytes(self.bob.stamp))
        self.treasure_map = self._treasure_map_class(m=m)
        self.expiration = expiration

        self._accepted_arrangements = set()    # type: Set[Arrangement]
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
        return {arrangement.ursula for arrangement in self._accepted_arrangements}

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
        return keccak_digest(bytes(self.alice.stamp) + bytes(self.bob.stamp) + self.label)

    async def put_treasure_map_on_node(self, node, network_middleware):
        treasure_map_id = self.treasure_map.public_id()
        response = network_middleware.put_treasure_map_on_node(
            node=node,
            map_id=treasure_map_id,
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

    def credential(self, with_treasure_map=True):
        """
        Creates a PolicyCredential for portable access to the policy via
        Alice or Bob. By default, it will include the treasure_map for the
        policy unless `with_treasure_map` is False.
        """
        from nucypher.policy.collections import PolicyCredential

        treasure_map = self.treasure_map
        if not with_treasure_map:
            treasure_map = None

        return PolicyCredential(self.alice.stamp, self.label, self.expiration,
                                self.public_key, treasure_map)

    def __assign_kfrags(self) -> Generator[Arrangement, None, None]:

        if len(self._accepted_arrangements) < self.n:
            raise self.MoreKFragsThanArrangements("Not enough candidate arrangements. "
                                                  "Call make_arrangements to make more.")

        for kfrag in self.kfrags:
            for arrangement in self._accepted_arrangements:
                if not arrangement in self._enacted_arrangements.values():
                    arrangement.kfrag = kfrag
                    self._enacted_arrangements[kfrag] = arrangement
                    yield arrangement
                    break  # This KFrag is now assigned; break the inner loop and go back to assign other kfrags.
            else:
                # We didn't assign that KFrag.  Trouble.
                # This is ideally an impossible situation, because we don't typically
                # enter this method unless we've already had n or more Arrangements accepted.
                raise self.MoreKFragsThanArrangements("Not enough accepted arrangements to assign all KFrags.")
        return

    def enact(self, network_middleware, publish_treasure_map=True) -> dict:
        """
        Assign kfrags to ursulas_on_network, and distribute them via REST,
        populating enacted_arrangements
        """
        for arrangement in self.__assign_kfrags():
            arrangement_message_kit = arrangement.encrypt_payload_for_ursula()

            try:
                # TODO: Concurrency
                response = network_middleware.enact_policy(arrangement.ursula,
                                                           arrangement.id,
                                                           arrangement_message_kit.to_bytes())
            except network_middleware.UnexpectedResponse as e:
                arrangement.status = e.status
            else:
                arrangement.status = response.status_code

            # TODO: Handle problem here - if the arrangement is bad, deal with it.
            self.treasure_map.add_arrangement(arrangement)

        else:
            # OK, let's check: if two or more Ursulas claimed we didn't pay,
            # we need to re-evaulate our situation here.
            arrangement_statuses = [a.status for a in self._accepted_arrangements]
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

    def propose_arrangement(self, network_middleware, ursula, arrangement) -> bool:
        negotiation_response = network_middleware.propose_arrangement(arrangement=arrangement)

        # TODO: check out the response: need to assess the result and see if we're actually good to go.
        arrangement_is_accepted = negotiation_response.status_code == 200

        bucket = self._accepted_arrangements if arrangement_is_accepted else self._rejected_arrangements
        bucket.add(arrangement)

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
            raise self.Rejected(f'Selected Ursulas rejected too many arrangements '
                                f'- only {len(self._accepted_arrangements)} of {self.n} accepted.')

    @abstractmethod
    def make_arrangement(self, ursula: Ursula, *args, **kwargs):
        raise NotImplementedError

    @abstractmethod
    def sample_essential(self, *args, **kwargs) -> Set[Ursula]:
        raise NotImplementedError

    def sample(self,
               handpicked_ursulas: Optional[Set[Ursula]] = None,
               discover_on_this_thread: bool = False,
               ) -> Set[Ursula]:
        selected_ursulas = set(handpicked_ursulas) if handpicked_ursulas else set()

        # Calculate the target sample quantity
        target_sample_quantity = self.n - len(selected_ursulas)
        if target_sample_quantity > 0:
            sampled_ursulas = self.sample_essential(quantity=target_sample_quantity,
                                                    handpicked_ursulas=selected_ursulas,
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
            arrangement = self.make_arrangement(ursula=selected_ursula, *args, **kwargs)
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
                    self._accepted_arrangements.add(arrangement)
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
                         quantity: int,
                         handpicked_ursulas: Set[Ursula],
                         discover_on_this_thread: bool = True) -> Set[Ursula]:
        self.alice.block_until_number_of_known_nodes_is(quantity, learn_on_this_thread=discover_on_this_thread)
        known_nodes = self.alice.known_nodes
        if handpicked_ursulas:
            # Prevent re-sampling of handpicked ursulas.
            known_nodes = set(known_nodes) - handpicked_ursulas
        sampled_ursulas = set(random.sample(k=quantity, population=list(known_nodes)))
        return sampled_ursulas

    def make_arrangement(self, ursula: Ursula, *args, **kwargs):
        return self._arrangement_class(alice=self.alice,
                                       expiration=self.expiration,
                                       ursula=ursula,
                                       *args, **kwargs)


class BlockchainPolicy(Policy):
    """
    A collection of n BlockchainArrangements representing a single Policy
    """
    _arrangement_class = BlockchainArrangement
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
                         quantity: int,
                         handpicked_ursulas: Set[Ursula],
                         learner_timeout: int = 1,
                         timeout: int = 10,
                         discover_on_this_thread: bool = False) -> Set[Ursula]: # TODO #843: Make timeout configurable

        selected_ursulas = set(handpicked_ursulas)
        quantity_remaining = quantity

        # Need to sample some stakers

        handpicked_addresses = [ursula.checksum_address for ursula in handpicked_ursulas]
        reservoir = self.alice.get_stakers_reservoir(duration=self.duration_periods,
                                                     without=handpicked_addresses)
        if len(reservoir) < quantity_remaining:
            error = f"Cannot create policy with {quantity} arrangements"
            raise self.NotEnoughBlockchainUrsulas(error)

        to_check = set(reservoir.draw(quantity_remaining))

        # Sample stakers in a loop and feed them to the learner to check
        # until we have enough in `selected_ursulas`.

        start_time = maya.now()
        new_to_check = to_check

        while True:

            # Check if the sampled addresses are already known.
            # If we're lucky, we won't have to wait for the learner iteration to finish.
            known = {x for x in to_check if x in self.alice.known_nodes}
            to_check = to_check - known

            known = random.sample(known, min(len(known), quantity_remaining)) # we only need so many
            selected_ursulas.update([self.alice.known_nodes[address] for address in known])
            quantity_remaining -= len(known)

            if quantity_remaining == 0:
                break
            else:
                new_to_check = reservoir.draw_at_most(quantity_remaining)
                to_check.update(new_to_check)

            delta = maya.now() - start_time
            if delta.total_seconds() >= timeout:
                still_checking = ', '.join(to_check)
                raise RuntimeError(f"Timed out after {timeout} seconds; "
                                   f"need {quantity_remaining} more, still checking {still_checking}.")

            self.alice.block_until_specific_nodes_are_known(to_check, learn_on_this_thread=discover_on_this_thread)

        found_ursulas = list(selected_ursulas)

        # Randomize the output to avoid the largest stakers always being the first in the list
        system_random = random.SystemRandom()
        system_random.shuffle(found_ursulas) # inplace

        return set(found_ursulas)

    def publish_to_blockchain(self) -> dict:

        prearranged_ursulas = list(a.ursula.checksum_address for a in self._accepted_arrangements)

        # Transact  # TODO: Move this logic to BlockchainPolicyActor
        receipt = self.author.policy_agent.create_policy(
            policy_id=self.hrac()[:16],  # bytes16 _policyID
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

    def make_arrangement(self, ursula: Ursula, *args, **kwargs):
        return self._arrangement_class(alice=self.alice,
                                       expiration=self.expiration,
                                       ursula=ursula,
                                       rate=self.rate,
                                       duration_periods=self.duration_periods,
                                       *args, **kwargs)

    def enact(self, network_middleware, publish_to_blockchain=True, publish_treasure_map=True) -> NodeEngagementMutex:
        """
        Assign kfrags to ursulas_on_network, and distribute them via REST,
        populating enacted_arrangements
        """
        if publish_to_blockchain is True:
            self.publish_to_blockchain()

            # Not in love with this block here, but I want 121 closed.
            for arrangement in self._accepted_arrangements:
                arrangement.publish_transaction = self.publish_transaction

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
