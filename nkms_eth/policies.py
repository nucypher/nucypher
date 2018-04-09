from nkms_eth.actors import Miner


class BlockchainArrangement:
    """
    A relationship between Alice and a single Ursula as part of Blockchain Policy
    """

    def __init__(self, author: str, miner: str, value: int, periods: int, arrangement_id: bytes=None):

        self.id = arrangement_id

        # The relationship exists between two addresses
        self.author = author
        self.policy_agent = author.policy_agent

        self.miner = miner

        # Arrangement value, rate, and duration
        rate = value // periods
        self._rate = rate

        self.value = value
        self.periods = periods  # TODO: datetime -> duration in blocks

        self.is_published = False

    def __repr__(self):
        class_name = self.__class__.__name__
        r = "{}(client={}, node={})"
        r = r.format(class_name, self.author, self.miner)
        return r

    def publish(self, gas_price: int) -> str:

        payload = {'from': self.author.address,
                   'value': self.value,
                   'gas_price': gas_price}


        txhash = self.policy_agent.transact(payload).createPolicy(self.id,
                                                                  self.miner.address,
                                                                  self.periods)

        self.policy_agent._blockchain._chain.wait.for_receipt(txhash)

        self.publish_transaction = txhash
        self.is_published = True
        return txhash

    def revoke(self, gas_price: int) -> str:
        """Revoke this arrangement and return the transaction hash as hex."""
        txhash = self.policy_agent.revoke_arrangement(self.id, author=self.author, gas_price=gas_price)
        self.revoke_transaction = txhash
        return txhash


class BlockchainPolicy:
    """TODO: A collection of n BlockchainArrangements representing a single Policy"""

    class NoSuchPolicy(Exception):
        pass

    def __init__(self):
        self._arrangements = list()

    def publish_arrangement(self, miner, periods: int, rate: int, arrangement_id: bytes=None) -> 'BlockchainArrangement':
        """
        Create a new arrangement to carry out a blockchain policy for the specified rate and time.
        """

        value = rate * periods
        arrangement = BlockchainArrangement(author=self,
                                            miner=miner,
                                            value=value,
                                            periods=periods)

        self._arrangements[arrangement.id] = {arrangement_id: arrangement}
        return arrangement

    def get_arrangement(self, arrangement_id: bytes) -> BlockchainArrangement:
        """Fetch a published arrangement from the blockchain"""

        blockchain_record = self.policy_agent.read().policies(arrangement_id)
        author_address, miner_address, rate, start_block, end_block, downtime_index = blockchain_record

        duration = end_block - start_block

        miner = Miner(address=miner_address, miner_agent=self.policy_agent.miner_agent)
        arrangement = BlockchainArrangement(author=self, miner=miner, periods=duration)

        arrangement.is_published = True
        return arrangement
