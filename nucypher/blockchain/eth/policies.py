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


from collections import deque

import math
import maya
from constant_sorrow.constants import UNKNOWN_ARRANGEMENTS, NON_PAYMENT
from typing import List
from typing import Set

from nucypher.blockchain.eth.actors import Miner
from nucypher.blockchain.eth.actors import PolicyAuthor
from nucypher.blockchain.eth.agents import MinerAgent, PolicyAgent
from nucypher.blockchain.eth.constants import HOURS_PER_PERIOD
from nucypher.blockchain.eth.utils import calculate_period_duration
from nucypher.characters.lawful import Ursula
from nucypher.network.middleware import RestMiddleware
from nucypher.policy.models import Arrangement, Policy


class BlockchainArrangement(Arrangement):
    """
    A relationship between Alice and a single Ursula as part of Blockchain Policy
    """
    federated = False

    def __init__(self,
                 alice: PolicyAuthor,
                 ursula: Miner,
                 value: int,
                 expiration: maya.MayaDT,
                 *args, **kwargs) -> None:

        super().__init__(alice=alice, ursula=ursula, expiration=expiration, *args, **kwargs)

        delta = expiration - maya.now()
        hours = (delta.total_seconds() / 60) / 60                               # type: int
        lock_periods = int(math.ceil(hours / HOURS_PER_PERIOD))  # type: int

        # The relationship exists between two addresses
        self.author = alice                     # type: PolicyAuthor
        self.policy_agent = alice.policy_agent  # type: PolicyAgent

        self.miner = ursula                     # type: Miner

        # Arrangement value, rate, and duration
        rate = value // lock_periods      # type: int
        self._rate = rate                 # type: int

        self.value = value                # type: int
        self.lock_periods = lock_periods  # type: int # TODO: <datetime> -> lock_periods

        self.is_published = False         # type: bool
        self.publish_transaction = None

        self.is_revoked = False           # type: bool
        self.revoke_transaction = None

    def __repr__(self):
        class_name = self.__class__.__name__
        r = "{}(client={}, node={})"
        r = r.format(class_name, self.author, self.miner)
        return r

    def revoke(self) -> str:
        """Revoke this arrangement and return the transaction hash as hex."""

        txhash = self.policy_agent.revoke_policy(self.id, author_address=self.author)
        self.revoke_transaction = txhash
        self.is_revoked = True
        return txhash


class BlockchainPolicy(Policy):
    """
    A collection of n BlockchainArrangements representing a single Policy
    """
    _arrangement_class = BlockchainArrangement

    class NoSuchPolicy(Policy):
        pass

    class NotEnoughBlockchainUrsulas(Policy.MoreKFragsThanArrangements):
        pass

    class Rejected(NotEnoughBlockchainUrsulas):
        """Too many Ursulas rejected"""

    def __init__(self,
                 alice: PolicyAuthor,
                 value: int,
                 expiration: maya.MayaDT,
                 handpicked_ursulas: set = None,
                 initial_reward: int = 0,  # TODO: move somewhere else?
                 *args, **kwargs):

        self.initial_reward = initial_reward
        self.lock_periods = int(calculate_period_duration(expiration))
        self.handpicked_ursulas = handpicked_ursulas or UNKNOWN_ARRANGEMENTS
        self.expiration = expiration
        self.value = value
        self.author = alice

        # Initial State
        self.publish_transaction = None
        self.is_published = False

        super().__init__(alice=alice, *args, **kwargs)

    def get_arrangement(self, arrangement_id: bytes) -> BlockchainArrangement:
        """Fetch published arrangements from the blockchain"""

        # Read from Blockchain
        blockchain_record = self.author.policy_agent.read().policies(arrangement_id)
        author_address, miner_address, rate, start_block, end_block, downtime_index = blockchain_record

        duration = end_block - start_block

        miner = Miner(address=miner_address, miner_agent=self.author.policy_agent.miner_agent, is_me=False)
        arrangement = BlockchainArrangement(alice=self.author,
                                            ursula=miner,
                                            value=rate*duration,   # TODO Check the math/types here
                                            lock_periods=duration,
                                            expiration=end_block)

        arrangement.is_published = True
        return arrangement

    def __find_ursulas(self,
                       ether_addresses: List[str],
                       target_quantity: int,
                       timeout: int = 10) -> Set[Ursula]:  # TODO #843: Make timeout configurable

        start_time = maya.now()                            # marker for timeout calculation

        found_ursulas, unknown_addresses = set(), deque()  # type: set, deque
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

        #  TODO #567: Figure out how to handle spare addresses (Buckets).
        # else:
        #     spare_addresses = ether_addresses  # Successfully collected and/or found n ursulas
        #     self.alice.nodes_to_seek.update((a for a in spare_addresses if a not in self.alice._known_nodes))

        return found_ursulas

    def make_arrangements(self, network_middleware: RestMiddleware, *args, **kwargs) -> None:
        """
        Create and consider n Arrangements from sampled miners, a list of Ursulas, or a combination of both.
        """

        # Prepare for selection
        if self.handpicked_ursulas is UNKNOWN_ARRANGEMENTS:
            handpicked_ursulas = set()
        else:
            handpicked_ursulas = self.handpicked_ursulas

        selected_addresses = set()

        # Calculate the target sample quantity
        ADDITIONAL_URSULAS = 1.5  # TODO: Make constant somewhere else
        target_sample_quantity = self.n - len(handpicked_ursulas)
        actual_sample_quantity = math.ceil(target_sample_quantity * ADDITIONAL_URSULAS)

        candidates = handpicked_ursulas
        if actual_sample_quantity > 0:
            # Sample by reading from the Blockchain
            try:
                sampled_addresses = self.alice.recruit(quantity=actual_sample_quantity, duration=self.lock_periods)

            except MinerAgent.NotEnoughMiners as e:
                error = "Cannot create policy with {} arrangements: {}".format(target_sample_quantity, e)
                raise self.NotEnoughBlockchainUrsulas(error)

            # Capture the selection and search the network for those Ursulas
            selected_addresses.update(sampled_addresses)
            found_ursulas = self.__find_ursulas(sampled_addresses, target_sample_quantity)

            # Get the difference (spares)
            spare_addresses = selected_addresses - set(u.checksum_public_address for u in found_ursulas)

            # Assemble the final selection
            candidates.update(found_ursulas)

        #
        # Consider Arrangements
        #

        # Attempt 1
        accepted, rejected = self._consider_arrangements(network_middleware=network_middleware,
                                                         candidate_ursulas=candidates,
                                                         value=self.value,
                                                         expiration=self.expiration)

        self._accepted_arrangements, self._rejected_arrangements = accepted, rejected

        # After all is said and done...
        if len(self._accepted_arrangements) < self.n:

            # Attempt 2:  Find more ursulas from the spare pile
            remaining_quantity = self.n - len(self._accepted_arrangements)

            # TODO: Handle spare Ursulas and try to claw back up to n.
            found_spare_ursulas = self.__find_ursulas(ether_addresses=list(spare_addresses),
                                                      target_quantity=remaining_quantity)

            accepted_spares, rejected_spares = self._consider_arrangements(network_middleware,
                                                                           candidate_ursulas=found_spare_ursulas,
                                                                           value=self.value,
                                                                           expiration=self.expiration)
            self._accepted_arrangements.update(accepted_spares)
            self._rejected_arrangements.update(rejected_spares)

            if len(accepted) < self.n:
                raise self.Rejected("Selected Ursulas rejected too many arrangements")

    def publish(self, **kwargs) -> str:

        if self.value is NON_PAYMENT:
            self.value = 0

        payload = {'from': self.author.checksum_public_address, 'value': self.value}
        prearranged_ursulas = list(a.ursula.checksum_public_address for a in self._accepted_arrangements)

        txhash = self.author.policy_agent.contract.functions.createPolicy(self.hrac()[:16],
                                                                          self.lock_periods,
                                                                          self.initial_reward,
                                                                          prearranged_ursulas,
                                                                          ).transact(payload)

        # Capture Response
        self.alice.policy_agent.blockchain.wait_for_receipt(txhash)
        self.publish_transaction = txhash
        self.is_published = True

        # Call super publish (currently publishes TMap)
        super().publish(network_middleware=self.alice.network_middleware)

        return txhash
