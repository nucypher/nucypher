from typing import Tuple

from .blockchain import Blockchain
from .escrow import Escrow
from .token import NuCypherKMSToken


class Miner:
    """Practically carrying a pickaxe"""

    def __init__(self, blockchain: Blockchain, token: NuCypherKMSToken, escrow: Escrow, address=None):
        self.blockchain = blockchain
        self.token = token
        self.address = address

        self.escrow = escrow
        if not escrow.contract:
            raise Escrow.ContractDeploymentError('Escrow contract not deployed. Arm then deploy.')
        else:
            escrow.miners.append(self)

    def __repr__(self):
        class_name = self.__class__.__name__
        r = "{}(address='{}')"
        r.format(class_name, self.address)

    def __del__(self):
        self.escrow.miners.remove(self)
        return None

    def _approve_escrow(self, amount: int) -> str:
        txhash = self.token.transact({'from': self.address}).approve(self.escrow.contract.address, amount)
        self.blockchain.chain.wait.for_receipt(txhash, timeout=self.blockchain.timeout)
        return txhash

    def _send_tokens_to_escrow(self, amount, locktime) -> str:
        deposit_txhash = self.escrow.transact({'from': self.address}).deposit(amount, locktime)
        self.blockchain.chain.wait.for_receipt(deposit_txhash, timeout=self.blockchain.timeout)
        return deposit_txhash

    def lock(self, amount: int, locktime: int) -> Tuple[str, str, str]:
        """Deposit and lock tokens for mining."""

        approve_txhash = self._approve_escrow(amount=amount)
        deposit_txhash = self._send_tokens_to_escrow(amount=amount, locktime=locktime)

        lock_txhash = self.escrow.transact({'from': self.address}).switchLock()
        self.blockchain.chain.wait.for_receipt(lock_txhash, timeout=self.blockchain.timeout)

        return approve_txhash, deposit_txhash, lock_txhash

    def mint(self) -> str:
        """Computes and transfers tokens to the miner's account"""
        txhash = self.escrow.transact({'from': self.address}).mint()
        self.blockchain.chain.wait.for_receipt(txhash, timeout=self.blockchain.timeout)
        return txhash

    def publish_dht_key(self, dht_id) -> str:
        """Store a new DHT key"""
        txhash = self.escrow.transact({'from': self.address}).publishDHTKey(dht_id)
        self.blockchain.chain.wait.for_receipt(txhash)
        return txhash

    def get_dht_key(self) -> tuple:
        """Retrieve all stored DHT keys for this miner"""
        count = self.escrow().getDHTKeysCount(self.address)
        dht_keys = tuple(self.escrow().getDHTKey(self.address, index) for index in range(count))
        return dht_keys

    def confirm_activity(self) -> str:
        """Miner rewarded for every confirmed period"""
        txhash = self.escrow.contract.transact({'from': self.address}).confirmActivity()
        self.blockchain.chain.wait.for_receipt(txhash)
        return txhash

    def balance(self) -> int:
        self.token._check_contract_deployment()
        balance = self.token().balanceOf(self.address)
        return balance

    def withdraw(self) -> str:
        """withdraw rewarded tokens"""
        txhash = self.escrow.transact({'from': self.address}).withdrawAll()
        self.blockchain.chain.wait.for_receipt(txhash, timeout=self.blockchain.timeout)
        return txhash
