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

import random
from abc import abstractmethod, ABC
from collections import OrderedDict, deque
from typing import Generator, Set, List

import maya
from bytestring_splitter import BytestringSplitter, VariableLengthBytestring
from constant_sorrow.constants import NOT_SIGNED, UNKNOWN_KFRAG, FEDERATED_POLICY, UNKNOWN_ARRANGEMENTS
from twisted.logger import Logger
from umbral.keys import UmbralPublicKey
from umbral.kfrags import KFrag

from nucypher.blockchain.eth.actors import BlockchainPolicyAuthor
from nucypher.blockchain.eth.agents import StakingEscrowAgent, PolicyManagerAgent
from nucypher.characters.lawful import Alice, Ursula
from nucypher.crypto.api import secure_random, keccak_digest
from nucypher.crypto.constants import PUBLIC_KEY_LENGTH
from nucypher.crypto.kits import RevocationKit
from nucypher.crypto.powers import DecryptingPower, SigningPower
from nucypher.crypto.utils import construct_policy_id
from nucypher.network.exceptions import NodeSeemsToBeDown
from nucypher.network.middleware import RestMiddleware


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
        self.author = alice                     # type: BlockchainPolicyAuthor
        self.policy_agent = alice.policy_agent  # type: PolicyManagerAgent
        self.staker = ursula                    # type: Ursula

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
        from nucypher.policy.collections import TreasureMap  # TODO: Circular Import

        self.alice = alice                     # type: Alice
        self.label = label                     # type: bytes
        self.bob = bob                         # type: Bob
        self.kfrags = kfrags                   # type: List[KFrag]
        self.public_key = public_key
        self.treasure_map = TreasureMap(m=m)
        self.expiration = expiration

        # Keep track of this stuff
        self.selection_buffer = 1

        self._accepted_arrangements = set()    # type: Set[Arrangement]
        self._rejected_arrangements = set()    # type: Set[Arrangement]
        self._spare_candidates = set()         # type: Set[Ursula]

        self._enacted_arrangements = OrderedDict()
        self._published_arrangements = OrderedDict()

        self.alice_signature = alice_signature  # TODO: This is unused / To Be Implemented?

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
        return construct_policy_id(self.label, bytes(self.bob.stamp))

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

    def publish_treasure_map(self, network_middleware: RestMiddleware) -> dict:
        self.treasure_map.prepare_for_publication(self.bob.public_keys(DecryptingPower),
                                                  self.bob.public_keys(SigningPower),
                                                  self.alice.stamp,
                                                  self.label)
        if not self.alice.known_nodes:
            # TODO: Optionally, block.
            raise RuntimeError("Alice hasn't learned of any nodes.  Thus, she can't push the TreasureMap.")

        responses = dict()
        self.log.debug(f"Pushing {self.treasure_map} to all known nodes from {self.alice}")
        for node in self.alice.known_nodes:
            # TODO: # 342 - It's way overkill to push this to every node we know about.  Come up with a system.

            try:
                treasure_map_id = self.treasure_map.public_id()

                # TODO: Certificate filepath needs to be looked up and passed here
                response = network_middleware.put_treasure_map_on_node(node=node,
                                                                       map_id=treasure_map_id,
                                                                       map_payload=bytes(self.treasure_map))
            except NodeSeemsToBeDown:
                # TODO: Introduce good failure mode here if too few nodes receive the map.
                self.log.debug(f"Failed pushing {self.treasure_map} to unresponsive {node}")
                continue

            if response.status_code == 202:
                # TODO: #341 - Handle response wherein node already had a copy of this TreasureMap.
                responses[node] = response
                self.log.debug(f"{self.treasure_map} successfully pushed to {node}")

            else:
                # TODO: Do something useful here.
                message = f"Failed pushing {self.treasure_map} to {node}, with status {response.status_code}"
                self.log.debug(message)
                raise RuntimeError(message)

        return responses

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

    def enact(self, network_middleware, publish=True) -> dict:
        """
        Assign kfrags to ursulas_on_network, and distribute them via REST,
        populating enacted_arrangements
        """
        for arrangement in self.__assign_kfrags():
            arrangement_message_kit = arrangement.encrypt_payload_for_ursula()

            try:
                response = network_middleware.enact_policy(arrangement.ursula,
                                                           arrangement.id,
                                                           arrangement_message_kit.to_bytes())
            except network_middleware.UnexpectedResponse as e:
                arrangement.status = e.status
            else:
                arrangement.status = response.status_code

            # Assuming response is what we hope for.
            self.treasure_map.add_arrangement(arrangement)

        else:
            # OK, let's check: if two or more Ursulas claimed we didn't pay,
            # we need to re-evaulate our situation here.
            arrangement_statuses = [a.status for a in self._accepted_arrangements]
            number_of_claims_of_freeloading = sum(status==402 for status in arrangement_statuses)

            if number_of_claims_of_freeloading > 2:
                raise self.alice.NotEnoughNodes  # TODO: Clean this up and enable re-tries.

            self.treasure_map.check_for_sufficient_destinations()

            # TODO: Leave a note to try any failures later.
            pass

            # ...After *all* the arrangements are enacted
            # Create Alice's revocation kit
            self.revocation_kit = RevocationKit(self, self.alice.stamp)
            self.alice.add_active_policy(self)

            if publish is True:
                return self.publish_treasure_map(network_middleware=network_middleware)

    def consider_arrangement(self, network_middleware, ursula, arrangement) -> bool:
        negotiation_response = network_middleware.consider_arrangement(arrangement=arrangement)

        # TODO: check out the response: need to assess the result and see if we're actually good to go.
        arrangement_is_accepted = negotiation_response.status_code == 200

        bucket = self._accepted_arrangements if arrangement_is_accepted else self._rejected_arrangements
        bucket.add(arrangement)

        return arrangement_is_accepted

    def make_arrangements(self,
                          network_middleware: RestMiddleware,
                          handpicked_ursulas: Set[Ursula] = None,
                          *args, **kwargs,
                          ) -> None:

        sampled_ursulas = self.sample(handpicked_ursulas=handpicked_ursulas)

        if len(sampled_ursulas) < self.n:
            raise self.MoreKFragsThanArrangements(
                "To make a Policy in federated mode, you need to designate *all* '  \
                 the Ursulas you need (in this case, {}); there's no other way to ' \
                 know which nodes to use.  Either pass them here or when you make ' \
                 the Policy.".format(self.n))

        # TODO: One of these layers needs to add concurrency.
        self._consider_arrangements(network_middleware=network_middleware,
                                    candidate_ursulas=sampled_ursulas,
                                    *args, **kwargs)

        if len(self._accepted_arrangements) < self.n:
            raise self.Rejected(f'Selected Ursulas rejected too many arrangements '
                                f'- only {len(self._accepted_arrangements)} of {self.n} accepted.')

    @abstractmethod
    def make_arrangement(self, ursula: Ursula, *args, **kwargs):
        raise NotImplementedError

    @abstractmethod
    def sample_essential(self, quantity: int, handpicked_ursulas: Set[Ursula] = None) -> Set[Ursula]:
        raise NotImplementedError

    def sample(self, handpicked_ursulas: Set[Ursula] = None) -> Set[Ursula]:
        selected_ursulas = set(handpicked_ursulas) if handpicked_ursulas else set()

        # Calculate the target sample quantity
        target_sample_quantity = self.n - len(selected_ursulas)
        if target_sample_quantity > 0:
            sampled_ursulas = self.sample_essential(quantity=target_sample_quantity,
                                                    handpicked_ursulas=handpicked_ursulas)
            selected_ursulas.update(sampled_ursulas)

        return selected_ursulas

    def _consider_arrangements(self,
                               network_middleware: RestMiddleware,
                               candidate_ursulas: Set[Ursula],
                               consider_everyone: bool = False,
                               *args,
                               **kwargs) -> None:

        for index, selected_ursula in enumerate(candidate_ursulas):
            arrangement = self.make_arrangement(ursula=selected_ursula, *args, **kwargs)
            try:
                is_accepted = self.consider_arrangement(ursula=selected_ursula,
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
                            spares = set(list(candidate_ursulas)[index+1::])
                            self._spare_candidates.update(spares)
                        except IndexError:
                            self._spare_candidates = set()
                        break
                else:
                    self.log.debug(f"Arrangement failed with {selected_ursula}")
                    self._rejected_arrangements.add(arrangement)


class FederatedPolicy(Policy):

    _arrangement_class = Arrangement

    def make_arrangements(self, *args, **kwargs) -> None:
        try:
            return super().make_arrangements(*args, **kwargs)
        except self.MoreKFragsThanArrangements:
            error = "To make a Policy in federated mode, you need to designate *all* '  \
                     the Ursulas you need (in this case, {}); there's no other way to ' \
                     know which nodes to use.  " \
                    "Pass them here as handpicked_ursulas.".format(self.n)
            raise self.MoreKFragsThanArrangements(error)  # TODO: NotEnoughUrsulas where in the exception tree is this?

    def sample_essential(self, quantity: int, handpicked_ursulas: Set[Ursula] = None) -> Set[Ursula]:
        known_nodes = self.alice.known_nodes
        if handpicked_ursulas:
            # Prevent re-sampling of handpicked ursulas.
            known_nodes = set(known_nodes) - set(handpicked_ursulas)
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

        self.selection_buffer = 1.5
        self.validate_reward_value()

    def validate_reward_value(self) -> None:
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

    def __find_ursulas(self,
                       ether_addresses: List[str],
                       target_quantity: int,
                       timeout: int = 10) -> set:  # TODO #843: Make timeout configurable

        start_time = maya.now()                            # marker for timeout calculation

        found_ursulas, unknown_addresses = set(), deque()
        while len(found_ursulas) < target_quantity:        # until there are enough Ursulas

            delta = maya.now() - start_time                # check for a timeout
            if delta.total_seconds() >= timeout:
                missing_nodes = ', '.join(a for a in unknown_addresses)
                raise RuntimeError("Timed out after {} seconds; Cannot find {}.".format(timeout, missing_nodes))

            # Select an ether_address: Prefer the selection pool, then unknowns queue
            if ether_addresses:
                ether_address = ether_addresses.pop()
            else:
                ether_address = unknown_addresses.popleft()

            try:
                # Check if this is a known node.
                selected_ursula = self.alice.known_nodes[ether_address]

            except KeyError:
                # Unknown Node
                self.alice.learn_about_specific_nodes({ether_address})  # enter address in learning loop
                unknown_addresses.append(ether_address)
                continue

            else:
                # Known Node
                found_ursulas.add(selected_ursula)  # We already knew, or just learned about this ursula

        return found_ursulas

    def sample_essential(self, quantity: int, handpicked_ursulas: Set[Ursula] = None) -> Set[Ursula]:
        # TODO: Prevent re-sampling of handpicked ursulas.
        selected_addresses = set()
        try:
            sampled_addresses = self.alice.recruit(quantity=quantity,
                                                   duration=self.duration_periods,
                                                   additional_ursulas=self.selection_buffer)
        except StakingEscrowAgent.NotEnoughStakers as e:
            error = f"Cannot create policy with {quantity} arrangements: {e}"
            raise self.NotEnoughBlockchainUrsulas(error)

        # Capture the selection and search the network for those Ursulas
        selected_addresses.update(sampled_addresses)
        found_ursulas = self.__find_ursulas(sampled_addresses, quantity)
        return found_ursulas

    def publish_to_blockchain(self) -> dict:

        prearranged_ursulas = list(a.ursula.checksum_address for a in self._accepted_arrangements)

        # Transact  # TODO: Move this logic to BlockchainPolicyActor
        receipt = self.author.policy_agent.create_policy(
                       policy_id=self.hrac()[:16],          # bytes16 _policyID
                       author_address=self.author.checksum_address,
                       value=self.value,
                       end_timestamp=self.expiration.epoch,           # uint16 _numberOfPeriods
                       node_addresses=prearranged_ursulas   # address[] memory _nodes
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

    def enact(self, network_middleware, publish=True) -> dict:
        """
        Assign kfrags to ursulas_on_network, and distribute them via REST,
        populating enacted_arrangements
        """
        if publish is True:
            self.publish_to_blockchain()

            # Not in love with this block here, but I want 121 closed.
            for arrangement in self._accepted_arrangements:
                arrangement.publish_transaction = self.publish_transaction

        return super().enact(network_middleware, publish)
