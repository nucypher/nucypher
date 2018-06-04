from nucypher.blockchain.eth.actors import Miner, PolicyAuthor


class BlockchainArrangement:
    """
    A relationship between Alice and a single Ursula as part of Blockchain Policy
    """

    def __init__(self, author, miner, value: int, lock_periods: int, arrangement_id: bytes=None):

        self.id = arrangement_id

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

        payload = {'from': self.author.address, 'value': self.value}

        txhash = self.policy_agent.contract.functions.createPolicy(self.id, self.miner.address, self.lock_periods).transact(payload)
        self.policy_agent.blockchain.wait.for_receipt(txhash)

        self.publish_transaction = txhash
        self.is_published = True
        return txhash

    def revoke(self, gas_price: int) -> str:
        """Revoke this arrangement and return the transaction hash as hex."""

        txhash = self.policy_agent.revoke_arrangement(self.id, author=self.author, gas_price=gas_price)
        self.revoke_transaction = txhash
        self.is_revoked = True
        return txhash


class BlockchainPolicy:
    """
    A collection of n BlockchainArrangements representing a single Policy
    """

    class NoSuchPolicy(Exception):
        pass

    def __init__(self, author: PolicyAuthor):
        self.author = author

    def get_arrangement(self, arrangement_id: bytes) -> BlockchainArrangement:
        """Fetch published arrangements from the blockchain"""

        blockchain_record = self.author.policy_agent.read().policies(arrangement_id)
        author_address, miner_address, rate, start_block, end_block, downtime_index = blockchain_record

        duration = end_block - start_block

        miner = Miner(address=miner_address, miner_agent=self.author.policy_agent.miner_agent)
        arrangement = BlockchainArrangement(author=self.author, miner=miner, lock_periods=duration)

        arrangement.is_published = True
        return arrangement
