
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
        if not address:
            address = self.blockchain.chain.web3.eth.accounts[0]

        tx = self.token.contract.transact({'from': address}).approve(self.escrow.contract.address, amount)
        self.blockchain.chain.wait.for_receipt(tx, timeout=self.blockchain.timeout)

        tx = self.escrow.contract.transact({'from': address}).deposit(amount, locktime)
        self.blockchain.chain.wait.for_receipt(tx, timeout=self.blockchain.timeout)

    # def unlock(self, address: str=None):
    #         if not address:
    #             address = chain.web3.eth.accounts[0]
    #         tx = self.escrow.contract.transact({'from': address}).switchLock()
    #         chain.wait.for_receipt(tx, timeout=chain.timeout)

    def mine(self, address: str=None):
        if not address:
            address = self.blockchain.web3.eth.accounts[0]

        tx = self.escrow.contract.transact({'from': address}).mint()
        self.blockchain.wait.for_receipt(tx, timeout=self.blockchain.timeout)

    def withdraw(self, address: str=None):
        if not address:
            address = self.blockchain.web3.eth.accounts[0]

        tx = self.escrow.contract.transact({'from': address}).withdrawAll()
        self.blockchain.wait.for_receipt(tx, timeout=self.blockchain.timeout)
