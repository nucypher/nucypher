from .blockchain import Blockchain
from .escrow import Escrow
from .token import NuCypherKMSToken


class Miner:
    """Practically carrying a pickaxe"""

    def __init__(self, blockchain: Blockchain, token: NuCypherKMSToken, escrow: Escrow):
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

        address = address or self.token.creator

        tx = self.token.transact({'from': address}).approve(self.escrow.contract.address, amount)
        self.blockchain.chain.wait.for_receipt(tx, timeout=self.blockchain.timeout)

        tx = self.escrow.transact({'from': address}).deposit(amount, locktime)
        self.blockchain.chain.wait.for_receipt(tx, timeout=self.blockchain.timeout)

        tx = self.escrow.transact({'from': address}).switchLock()
        self.blockchain.chain.wait.for_receipt(tx, timeout=self.blockchain.timeout)

    def mine(self, address: str=None) -> str:
        address = address or self.token.creator
        tx = self.escrow.transact({'from': address}).mint()
        self.blockchain.chain.wait.for_receipt(tx, timeout=self.blockchain.timeout)
        return tx

    def withdraw(self, address: str=None) -> str:
        address = address or self.token.creator
        tx = self.escrow.transact({'from': address}).withdrawAll()
        self.blockchain.chain.wait.for_receipt(tx, timeout=self.blockchain.timeout)
        return tx