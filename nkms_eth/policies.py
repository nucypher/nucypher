class PolicyArrangement:
    """
    A relationship between Alice and a single Ursula as part of Blockchain Policy
    """

    def __init__(self, author, miner, value: int, periods: int, arrangement_id: bytes=None):

        if arrangement_id is None:
            self.id = self.__class__._generate_arrangement_id()  # TODO: Generate policy ID

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

    @staticmethod
    def _generate_arrangement_id(policy_hrac: bytes) -> bytes:
        pass  # TODO

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

    def __update_periods(self) -> None:
        blockchain_record = self.policy_agent.fetch_arrangement_data(self.id)
        client, delegate, rate, *periods = blockchain_record
        self._elapsed_periods = periods

    def revoke(self, gas_price: int) -> str:
        """Revoke this arrangement and return the transaction hash as hex."""
        txhash = self.policy_agent.revoke_arrangement(self.id, author=self.author, gas_price=gas_price)
        self.revoke_transaction = txhash
        return txhash


class BlockchainPolicy:
    """A collection of n BlockchainArrangements representing a single Policy"""

    class NoSuchPolicy(Exception):
        pass

    def __init__(self):
        self._arrangements = list()
