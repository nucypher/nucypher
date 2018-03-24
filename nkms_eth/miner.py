from typing import Tuple

from .blockchain import Blockchain
from .escrow import Escrow
from .token import NuCypherKMSToken


class Miner:
    """
    Practically carrying a pickaxe.
    Intended for use as an Ursula mixin.

    Accepts a running blockchain, deployed token contract, and deployed escrow contract.
    If the provided token and escrow contracts are not deployed,
    ContractDeploymentError will be raised.

    """

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
        """Removes this miner from the escrow's list of miners on delete."""
        self.escrow.miners.remove(self)

    def _approve_escrow(self, amount: int) -> str:
        """Approve the transfer of token from the miner's address to the escrow contract."""

        txhash = self.token.transact({'from': self.address}).approve(self.escrow.contract.address, amount)
        self.blockchain._chain.wait.for_receipt(txhash, timeout=self.blockchain._timeout)

        return txhash

    def _send_tokens_to_escrow(self, amount, locktime) -> str:
        """Send tokes to the escrow from the miner's address"""

        deposit_txhash = self.escrow.transact({'from': self.address}).deposit(amount, locktime)
        self.blockchain._chain.wait.for_receipt(deposit_txhash, timeout=self.blockchain._timeout)

        return deposit_txhash

    def lock(self, amount: int, locktime: int) -> Tuple[str, str, str]:
        """Deposit and lock tokens for mining."""

        approve_txhash = self._approve_escrow(amount=amount)
        deposit_txhash = self._send_tokens_to_escrow(amount=amount, locktime=locktime)

        lock_txhash = self.escrow.transact({'from': self.address}).switchLock()
        self.blockchain._chain.wait.for_receipt(lock_txhash, timeout=self.blockchain._timeout)

        return approve_txhash, deposit_txhash, lock_txhash

    def mint(self) -> str:
        """Computes and transfers tokens to the miner's account"""

        txhash = self.escrow.transact({'from': self.address}).mint()
        self.blockchain._chain.wait.for_receipt(txhash, timeout=self.blockchain._timeout)

        return txhash

    # TODO
    # def collect_reward(self):
    #     tx = policy_manager.transact({'from': self.address}).withdraw()
    #     chain.wait.for_receipt(tx)

    def publish_dht_key(self, dht_id) -> str:
        """Store a new DHT key"""

        txhash = self.escrow.transact({'from': self.address}).setMinerId(dht_id)
        self.blockchain._chain.wait.for_receipt(txhash)

        return txhash

    def get_dht_key(self) -> tuple:
        """Retrieve all stored DHT keys for this miner"""

        count = self.blockchain._chain.web3.toInt(
            self.escrow().getMinerInfo(self.escrow.MinerInfoField.MINER_IDS_LENGTH.value, self.address, 0)
                .encode('latin-1'))
        # TODO change when v4 web3.py will released
        dht_keys = tuple(self.escrow().getMinerInfo(self.escrow.MinerInfoField.MINER_ID.value, self.address, index)
                         .encode('latin-1') for index in range(count))

        return dht_keys

    def confirm_activity(self) -> str:
        """Miner rewarded for every confirmed period"""

        txhash = self.escrow.contract.transact({'from': self.address}).confirmActivity()
        self.blockchain._chain.wait.for_receipt(txhash)

        return txhash

    def balance(self) -> int:
        """Check miner's current balance"""

        self.token._check_contract_deployment()
        balance = self.token().balanceOf(self.address)

        return balance

    def withdraw(self) -> str:
        """withdraw rewarded tokens"""
        tokens_amount = self.blockchain._chain.web3.toInt(
            self.escrow().getMinerInfo(self.escrow.MinerInfoField.VALUE.value, self.address, 0).encode('latin-1'))
        txhash = self.escrow.transact({'from': self.address}).withdraw(tokens_amount)
        self.blockchain._chain.wait.for_receipt(txhash, timeout=self.blockchain._timeout)

        return txhash
