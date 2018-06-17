import math
from typing import List
from typing import Set

import maya
from collections import deque

from constant_sorrow import constants
from nucypher.blockchain.eth.actors import Miner
from nucypher.blockchain.eth.actors import PolicyAuthor
from nucypher.blockchain.eth.agents import MinerAgent
from nucypher.blockchain.eth.constants import calculate_period_duration
from nucypher.characters import Ursula
from nucypher.network.middleware import RestMiddleware
from nucypher.policy.models import Arrangement, Policy


class BlockchainArrangement(Arrangement):
    """
    A relationship between Alice and a single Ursula as part of Blockchain Policy
    """

    def __init__(self, author: PolicyAuthor,
                 miner: Miner,
                 value: int,
                 lock_periods: int,
                 *args, **kwargs):
        super().__init__(alice=author, ursula=miner, *args, **kwargs)

        # The relationship exists between two addresses
        self.author = author
        self.policy_agent = author.policy_agent

        self.miner = miner

        # Arrangement value, rate, and duration
        rate = value // lock_periods
        self._rate = rate

        self.value = value
        self.lock_periods = lock_periods  # TODO: <datetime> -> lock_periods

        self.is_published = False
        self.publish_transaction = None

        self.is_revoked = False
        self.revoke_transaction = None

    def __repr__(self):
        class_name = self.__class__.__name__
        r = "{}(client={}, node={})"
        r = r.format(class_name, self.author, self.miner)
        return r

    def publish(self) -> str:
        payload = {'from': self.author.ether_address, 'value': self.value}

        txhash = self.policy_agent.contract.functions.createPolicy(self.id, self.miner.ether_address,
                                                                   self.lock_periods).transact(payload)
        self.policy_agent.blockchain.wait_for_receipt(txhash)

        self.publish_transaction = txhash
        self.is_published = True
        return txhash

    def revoke(self) -> str:
        """Revoke this arrangement and return the transaction hash as hex."""

        txhash = self.policy_agent.revoke_policy(self.id, author=self.author)
        self.revoke_transaction = txhash
        self.is_revoked = True
        return txhash


class BlockchainPolicy(Policy):
    """
    A collection of n BlockchainArrangements representing a single Policy
    """

    class NoSuchPolicy(Exception):
        pass

    class NotEnoughBlockchainUrsulas(Exception):
        pass

    def __init__(self, author: PolicyAuthor, *args, **kwargs):
        self.author = author
        super().__init__(alice=author, *args, **kwargs)

    def get_arrangement(self, arrangement_id: bytes) -> BlockchainArrangement:
        """Fetch published arrangements from the blockchain"""

        blockchain_record = self.author.policy_agent.read().policies(arrangement_id)
        author_address, miner_address, rate, start_block, end_block, downtime_index = blockchain_record

        duration = end_block - start_block

        miner = Miner(address=miner_address, miner_agent=self.author.policy_agent.miner_agent)
        arrangement = BlockchainArrangement(author=self.author, miner=miner, lock_periods=duration)

        arrangement.is_published = True
        return arrangement

    def __find_ursulas(self, ether_addresses: List[str], target_quantity: int, timeout: int = 120):
        start_time = maya.now()  # Marker for timeout calculation
        found_ursulas, unknown_addresses = set(), deque()
        while len(found_ursulas) < target_quantity:

            # Check for a timeout
            delta = maya.now() - start_time
            if delta.total_seconds() >= timeout:
                raise RuntimeError("Timeout: cannot find ursulas.")  # TODO: Better exception

            # Select an ether_address: Prefer the selection pool, then unknowns queue
            if ether_addresses:
                ether_address = bytes(ether_addresses.pop(), encoding="ascii")
            else:
                ether_address = unknown_addresses.popleft()

            try:
                # Check if this is a known node.
                selected_ursula = self.alice._known_nodes[ether_address]

            except KeyError:
                # Unknown Node
                self.alice.learn_about_specific_node(ether_address)  # enter address in learning loop
                unknown_addresses.append(ether_address)
                continue

            else:
                # Known Node
                found_ursulas.add(selected_ursula)  # We already knew, or just learned about this ursula

        #  TODO: Figure out how to handle spare addresses.
        # else:
        #     spare_addresses = ether_addresses  # Successfully collected and/or found n ursulas
        #     self.alice.nodes_to_seek.update((a for a in spare_addresses if a not in self.alice.known_nodes))

        return found_ursulas

    def __consider_arrangements(self, network_middleware, candidate_ursulas: Set[Ursula],
                                deposit: int, expiration: maya.MayaDT) -> tuple:

        accepted, rejected = set(), set()
        for selected_ursula in candidate_ursulas:

            delta = expiration - maya.now()
            hours = (delta.total_seconds() / 60) / 60
            periods = int(math.ceil(hours / int(constants.HOURS_PER_PERIOD)))

            blockchain_arrangement = BlockchainArrangement(author=self.alice, miner=selected_ursula,
                                                           value=deposit, lock_periods=periods,
                                                           expiration=expiration, hrac=self.hrac)

            ursula_accepts = self.consider_arrangement(ursula=selected_ursula,
                                                       arrangement=blockchain_arrangement,
                                                       network_middleware=network_middleware)

            if ursula_accepts:  # TODO: Read the negotiation results from REST
                accepted.add(blockchain_arrangement)
            else:
                rejected.add(blockchain_arrangement)

        return accepted, rejected

    def make_arrangements(self, network_middleware: RestMiddleware,
                          deposit: int, expiration: maya.MayaDT,
                          handpicked_ursulas: Set[Ursula] = set()) -> None:
        """
        Create and consider n Arrangements from sampled miners, a list of Ursulas, or a combination of both.
        """

        ADDITIONAL_URSULAS = 1.5  # TODO: Make constant

        target_sample_quantity = self.n - len(handpicked_ursulas)

        selected_addresses = set()
        try:  # Sample by reading from the Blockchain
            actual_sample_quantity = math.ceil(target_sample_quantity * ADDITIONAL_URSULAS)
            duration = int(calculate_period_duration(expiration))
            sampled_addresses = self.alice.recruit(quantity=actual_sample_quantity,
                                                   duration=duration,
                                                   )
        except MinerAgent.NotEnoughMiners:
            error = "Cannot create policy with {} arrangements."
            raise self.NotEnoughBlockchainUrsulas(error.format(self.n))
        else:
            selected_addresses.update(sampled_addresses)

        found_ursulas = self.__find_ursulas(sampled_addresses, target_sample_quantity)

        candidates = handpicked_ursulas
        candidates.update(found_ursulas)

        #
        # Consider Arrangements
        #

        # Attempt 1
        accepted, rejected = self.__consider_arrangements(network_middleware, candidate_ursulas=candidates,
                                                          deposit=deposit, expiration=expiration)

        # After all is said and done...
        if len(accepted) < self.n:

            # Attempt 2:  Find more ursulas from the spare pile
            remaining_quantity = self.n - len(accepted)

            # TODO: Handle spare Ursulas and try to claw back up to n.
            assert False
            found_spare_ursulas, remaining_spare_addresses = self.__find_ursulas(spare_addresses, remaining_quantity)
            accepted_spares, rejected_spares = self.__consider_arrangements(network_middleware,
                                                                            candidate_ursulas=found_spare_ursulas,
                                                                            deposit=deposit, expiration=expiration)
            accepted.update(accepted_spares)
            rejected.update(rejected_spares)

            if len(accepted) < self.n:
                raise Exception("Selected Ursulas rejected too many arrangements")  # TODO: Better exception

        self._accepted_arrangements.update(accepted)
        self._rejected_arrangements.append(rejected)
