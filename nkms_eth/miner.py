from typing import Tuple

from .escrow import MinerEscrow


class Miner:
    """
    Practically carrying a pickaxe.
    Intended for use as an Ursula mixin.

    Accepts a running blockchain, deployed token contract, and deployed escrow contract.
    If the provided token and escrow contracts are not deployed,
    ContractDeploymentError will be raised.

    """

    def __init__(self, escrow: MinerEscrow, address=None):

        self.escrow = escrow
        if not escrow._contract:
            raise MinerEscrow.ContractDeploymentError('Escrow contract not deployed. Arm then deploy.')
        else:
            escrow.miners.append(self)

        self._token = escrow.token
        self._blockchain = self._token.blockchain

        self.address = address
        self._transactions = []
        self._locked_tokens = self._update_locked_tokens()

    def __repr__(self):
        class_name = self.__class__.__name__
        r = "{}(address='{}')"
        r.format(class_name, self.address)
        return r

    def __del__(self):
        """Removes this miner from the escrow's list of miners on delete."""
        self.escrow.miners.remove(self)

    def _update_locked_tokens(self) -> None:
        self._locked_tokens = self.escrow().getLockedTokens(self.address)

    def _approve_escrow(self, amount: int) -> str:
        """Approve the transfer of token from the miner's address to the escrow contract."""

        txhash = self._token.transact({'from': self.address}).approve(self.escrow._contract.address, amount)
        self._blockchain._chain.wait.for_receipt(txhash, timeout=self._blockchain._timeout)

        self._transactions.append(txhash)

        return txhash

    def _send_tokens_to_escrow(self, amount, locktime) -> str:
        """Send tokes to the escrow from the miner's address"""

        deposit_txhash = self.escrow.transact({'from': self.address}).deposit(amount, locktime)
        self._blockchain._chain.wait.for_receipt(deposit_txhash, timeout=self._blockchain._timeout)

        self._transactions.append(deposit_txhash)

        return deposit_txhash

    def lock(self, amount: int, locktime: int) -> Tuple[str, str, str]:
        """Deposit and lock tokens for mining."""

        approve_txhash = self._approve_escrow(amount=amount)
        deposit_txhash = self._send_tokens_to_escrow(amount=amount, locktime=locktime)

        lock_txhash = self.escrow.transact({'from': self.address}).switchLock()
        self._blockchain._chain.wait.for_receipt(lock_txhash, timeout=self._blockchain._timeout)

        self._transactions.extend([approve_txhash, deposit_txhash, lock_txhash])

        return approve_txhash, deposit_txhash, lock_txhash

    def confirm_activity(self) -> str:
        """Miner rewarded for every confirmed period"""

        txhash = self.escrow.transact({'from': self.address}).confirmActivity()
        self._blockchain._chain.wait.for_receipt(txhash)

        self._transactions.append(txhash)

        return txhash

    def mint(self) -> str:
        """Computes and transfers tokens to the miner's account"""

        txhash = self.escrow.transact({'from': self.address}).mint()
        self._blockchain._chain.wait.for_receipt(txhash, timeout=self._blockchain._timeout)

        self._transactions.append(txhash)

        return txhash

    def collect_policy_reward(self, policy_manager):
        """Collect policy reward in ETH"""

        txhash = policy_manager.transact({'from': self.address}).withdraw()
        self._blockchain._chain.wait.for_receipt(txhash)

        self._transactions.append(txhash)

        return txhash

    def publish_miner_id(self, miner_id) -> str:
        """Store a new Miner ID"""

        txhash = self.escrow.transact({'from': self.address}).setMinerId(miner_id)
        self._blockchain._chain.wait.for_receipt(txhash)

        self._transactions.append(txhash)

        return txhash

    def fetch_miner_ids(self) -> tuple:
        """Retrieve all stored Miner IDs on this miner"""

        count = self.escrow().getMinerInfo(self.escrow.MinerInfoField.MINER_IDS_LENGTH.value,
                                           self.address,
                                           0).encode('latin-1')

        count = self._blockchain._chain.web3.toInt(count)

        # TODO change when v4 web3.py will released
        miner_ids = tuple(self.escrow().getMinerInfo(self.escrow.MinerInfoField.MINER_ID.value, self.address, index)
                          .encode('latin-1') for index in range(count))

        return tuple(miner_ids)

    def eth_balance(self):
        return self._blockchain._chain.web3.eth.getBalance(self.address)

    def token_balance(self) -> int:
        """Check miner's current token balance"""

        self._token._check_contract_deployment()
        balance = self._token().balanceOf(self.address)

        return balance

    def withdraw(self, amount: int=0, entire_balance=False) -> str:
        """Withdraw tokens"""

        tokens_amount = self._blockchain._chain.web3.toInt(
            self.escrow().getMinerInfo(self.escrow.MinerInfoField.VALUE.value, self.address, 0).encode('latin-1'))

        txhash = self.escrow.transact({'from': self.address}).withdraw(tokens_amount)

        self._blockchain._chain.wait.for_receipt(txhash, timeout=self._blockchain._timeout)

        if entire_balance and amount:
            raise Exception("Specify an amount or entire balance, not both")

        if entire_balance:
            txhash = self.escrow.transact({'from': self.address}).withdraw(tokens_amount)
        else:
            txhash = self.escrow.transact({'from': self.address}).withdraw(amount)

        self._transactions.append(txhash)
        self._blockchain._chain.wait.for_receipt(txhash, timeout=self._blockchain._timeout)

        return txhash
