import math
import random
from typing import List, Set

import maya
from constant_sorrow import constants

from nucypher.blockchain.eth.actors import PolicyAuthor

from nucypher.blockchain.eth.actors import Miner
from nucypher.blockchain.eth.agents import MinerAgent
from nucypher.characters import Ursula
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
        self.policy_agent.blockchain.wait.for_receipt(txhash)

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

    def make_arrangements(self, network_middleware,
                          deposit: int, expiration: maya.MayaDT,
                          ursulas: Set[Ursula]=None, timeout=120) -> None:
        """
        Create and consider n Arrangements from sampled miners, a list of Ursulas, or a combination of both.
        """
        #
        # Determine Samples
        #
        selected_ursulas = set()

        handpicked_ursulas = ursulas  # hand-picked ursulas
        additional_ursulas = len(handpicked_ursulas) - self.n
        selected_ursulas.update(handpicked_ursulas)

        sample_quantity = self.n if ursulas is None else additional_ursulas

        #
        # Sample
        #
        if len(handpicked_ursulas) < self.n:

            selected_addresses = set()
            try:  # Sample by reading from the Blockchain
                sampled_addresses = self.alice.recruit(quantity=sample_quantity)
            except MinerAgent.NotEnoughMiners:
                error = "Cannot create policy with {} arrangements."
                raise self.NotEnoughBlockchainUrsulas(error.format(self.n))
            else:
                selected_addresses.update(sampled_addresses)

            #
            # Find Ursulas
            #
            start_time = maya.now()  # Marker for timeout calculation
            unknown_nodes = set()
            while len(selected_ursulas) < self.n:

                # Prefer the selection pool, then unknowns
                if selected_addresses:
                    ether_address = selected_addresses.pop()

                else:
                    delta = maya.now() - start_time
                    if delta.total_seconds() >= timeout:
                        raise Exception("Timeout")  # TODO: Better exception

                    ether_address = unknown_nodes.pop()

                try:
                    # Check if this is a known node.
                    selected_ursula = self.alice.known_nodes.get[ether_address]
                except KeyError:

                    # We don't know about this ursula, yet
                    unknown_nodes.add(ether_address)

                    # If we're not already looking for this node, start looking!
                    if ether_address not in self.alice.nodes_to_seek:
                        self.alice.nodes_to_seek.add(ether_address)
                        continue
                else:
                    # We already knew about this ursula
                    selected_ursulas.add(selected_ursula)

            else:
                candidate_ursulas = random.sample(selected_ursulas, sample_quantity)


            #
            # Consider Arrangements
            #
            accepted, rejected = set(), set()
            for selected_ursula in candidate_ursulas:

                delta = expiration - maya.now()
                hours = (delta.total_seconds()/60) / 60
                periods = int(math.ceil(hours/int(constants.HOURS_PER_PERIOD)))

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

            else:
                # After all is said and done...
                if len(accepted) < self.n:
                    raise Exception("Selected Ursulas rejected too many arrangements")  # TODO: Better exception

                self._accepted_arrangements.update(accepted)
                self._rejected_arrangements.append(rejected)
