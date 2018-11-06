"""
This file is part of nucypher.

nucypher is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

nucypher is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with nucypher.  If not, see <https://www.gnu.org/licenses/>.
"""
from collections import deque

import math
import maya
from constant_sorrow import constants
from typing import List
from typing import Set

from nucypher.blockchain.eth.actors import Miner
from nucypher.blockchain.eth.actors import PolicyAuthor
from nucypher.blockchain.eth.agents import MinerAgent, PolicyAgent
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
                 author: PolicyAuthor,
                 miner: Miner,
                 value: int,
                 expiration: maya.MayaDT,
                 *args, **kwargs) -> None:

        super().__init__(alice=author, ursula=miner, *args, **kwargs)

        delta = expiration - maya.now()
        hours = (delta.total_seconds() / 60) / 60                               # type: int
        lock_periods = int(math.ceil(hours / int(constants.HOURS_PER_PERIOD)))  # type: int

        # The relationship exists between two addresses
        self.author = author                     # type: PolicyAuthor
        self.policy_agent = author.policy_agent  # type: PolicyAgent

        self.miner = miner                # type: Miner

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

    def publish(self) -> str:
        payload = {'from': self.author.checksum_public_address,
                   'value': self.value}

        txhash = self.policy_agent.contract.functions.createPolicy(self.id,
                                                                   self.miner.checksum_public_address,
                                                                   self.lock_periods).transact(payload)
        self.policy_agent.blockchain.wait_for_receipt(txhash)

        self.publish_transaction = txhash
        self.is_published = True
        return txhash

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

    class NoSuchPolicy(Exception):
        pass

    class NotEnoughBlockchainUrsulas(Exception):
        pass

    def __init__(self,
                 author: PolicyAuthor,
                 *args, **kwargs
                 ) -> None:

        self.author = author
        super().__init__(alice=author, *args, **kwargs)

    def get_arrangement(self, arrangement_id: bytes) -> BlockchainArrangement:
        """Fetch published arrangements from the blockchain"""

        blockchain_record = self.author.policy_agent.read().policies(arrangement_id)
        author_address, miner_address, rate, start_block, end_block, downtime_index = blockchain_record

        duration = end_block - start_block

        miner = Miner(address=miner_address, miner_agent=self.author.policy_agent.miner_agent)
        arrangement = BlockchainArrangement(author=self.author,
                                            miner=miner,
                                            value=rate*duration,   # TODO Check the math/types here
                                            lock_periods=duration,
                                            expiration=end_block)  # TODO: fix missing argument here

        arrangement.is_published = True
        return arrangement

    def __find_ursulas(self,
                       ether_addresses: List[str],
                       target_quantity: int,
                       timeout: int = 10) -> Set[Ursula]:  # TODO: Make timeout configurable

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

        #  TODO: Figure out how to handle spare addresses.
        # else:
        #     spare_addresses = ether_addresses  # Successfully collected and/or found n ursulas
        #     self.alice.nodes_to_seek.update((a for a in spare_addresses if a not in self.alice._known_nodes))

        return found_ursulas

    def make_arrangements(self,
                          network_middleware: RestMiddleware,
                          deposit: int,
                          expiration: maya.MayaDT,
                          handpicked_ursulas: Set[Ursula] = None
                          ) -> None:
        """
        Create and consider n Arrangements from sampled miners, a list of Ursulas, or a combination of both.
        """

        ADDITIONAL_URSULAS = 1.5        # TODO: Make constant

        handpicked_ursulas = handpicked_ursulas or set()           # type: set
        target_sample_quantity = self.n - len(handpicked_ursulas)

        selected_addresses = set()      # type: set
        actual_sample_quantity = math.ceil(target_sample_quantity * ADDITIONAL_URSULAS)
        duration = int(calculate_period_duration(expiration))

        try:  # Sample by reading from the Blockchain
            sampled_addresses = self.alice.recruit(quantity=actual_sample_quantity, duration=duration)
        except MinerAgent.NotEnoughMiners as e:
            error = "Cannot create policy with {} arrangements: {}".format(target_sample_quantity, e)
            raise self.NotEnoughBlockchainUrsulas(error)

        selected_addresses.update(sampled_addresses)
        found_ursulas = self.__find_ursulas(sampled_addresses, target_sample_quantity)

        candidates = handpicked_ursulas
        candidates.update(found_ursulas)

        #
        # Consider Arrangements
        #

        # Attempt 1
        accepted, rejected = self._consider_arrangements(network_middleware=network_middleware,
                                                         candidate_ursulas=candidates,
                                                         deposit=deposit,
                                                         expiration=expiration)
        # After all is said and done...
        if len(accepted) < self.n:

            # Attempt 2:  Find more ursulas from the spare pile
            remaining_quantity = self.n - len(accepted)

            # TODO: Handle spare Ursulas and try to claw back up to n.
            found_spare_ursulas, remaining_spare_addresses = self.__find_ursulas(spare_addresses, remaining_quantity)
            accepted_spares, rejected_spares = self._consider_arrangements(network_middleware,
                                                                           candidate_ursulas=found_spare_ursulas,
                                                                           deposit=deposit,
                                                                           expiration=expiration)
            accepted.update(accepted_spares)
            rejected.update(rejected_spares)

            if len(accepted) < self.n:
                raise Exception("Selected Ursulas rejected too many arrangements")  # TODO: Better exception

    def publish(self, network_middleware) -> None:
        """Publish enacted arrangements."""

        if not self._enacted_arrangements:
            raise RuntimeError("There are no enacted arrangements to publish to the network.")

        while len(self._enacted_arrangements) > 0:
            kfrag, arrangement = self._enacted_arrangements.popitem()
            arrangement.publish()

        super().publish(network_middleware)
