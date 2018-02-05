
class Miner:
    """Practically carrying a pickaxe"""

    def __init__(self, blockchain, token, escrow):
        self.blockchain = blockchain
        self.escrow = escrow
        self.token = token

    def lock(self, amount: int, locktime: int, address: str=None):
        """
        Deposit and lock coins for mining.
        Creating coins starts after it is done.

        :param amount:      Amount of coins to lock (in smallest  indivisible units)
        :param locktime:    Locktime in periods
        :param address:     Optional address to get coins from (accounts[0] by default)
        """

        with self.blockchain as chain:
            address = address or chain.web3.eth.accounts[0]
            token = self.escrow

            tx = token.contract.transact({'from': address}).approve(self.escrow.contract.address, amount)
            chain.wait.for_receipt(tx, timeout=chain.timeout)

            tx = self.escrow.contract.transact({'from': address}).deposit(amount, locktime)
            chain.wait.for_receipt(tx, timeout=chain.timeout)

            tx = self.escrow.contract.transact({'from': address}).switchLock()
            chain.wait.for_receipt(tx, timeout=chain.timeout)

    def mine(self, address: str=None):
        with self.blockchain as chain:
            if not address:
                address = chain.web3.eth.accounts[0]

            tx = self.escrow.contract.transact({'from': address}).mint()
            chain.wait.for_receipt(tx, timeout=self.blockchain.timeout)

    def withdraw(self, address: str=None):
        with self.blockchain as chain:
            if not address:
                address = chain.web3.eth.accounts[0]

            tx = self.escrow.contract.transact({'from': address}).withdrawAll()
            chain.wait.for_receipt(tx, timeout=self.blockchain.timeout)
