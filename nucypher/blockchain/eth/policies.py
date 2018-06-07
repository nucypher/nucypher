import math
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

        txhash = self.policy_agent.revoke_arrangement(self.id, author=self.author)
        self.revoke_transaction = txhash
        self.is_revoked = True
        return txhash


class BlockchainPolicy(Policy):
    """
    A collection of n BlockchainArrangements representing a single Policy
    """

    class NoSuchPolicy(Exception):
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

    def make_arrangements(self, network_middleware, quantity: int,
                          deposit: int, expiration: maya.MayaDT, ursulas: Set[Ursula]=None) -> None:
        """
        Create and consider n Arangement objects from sampled miners.
        """

        if ursulas is not None:
            # if len(ursulas) < self.n:
            #     raise Exception # TODO: Validate ursulas
            pass

        else:
            try:
                sampled_miners = self.alice.recruit(quantity=quantity or self.n)
            except MinerAgent.NotEnoughMiners:
                raise  # TODO
            else:
                ursulas = (Ursula.from_miner(miner, is_me=False) for miner in sampled_miners)

        for ursula in ursulas:

            delta = expiration - maya.now()
            hours = (delta.total_seconds() / 60) / 60
            periods = int(math.ceil(hours / int(constants.HOURS_PER_PERIOD)))

            blockchain_arrangement = BlockchainArrangement(author=self.alice, miner=ursula,
                                                           value=deposit, lock_periods=periods,
                                                           expiration=expiration, hrac=self.hrac)

            self.consider_arrangement(network_middleware=network_middleware,
                                      arrangement=blockchain_arrangement)
