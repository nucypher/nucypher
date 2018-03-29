from abc import ABC
from collections import OrderedDict
from datetime import datetime
from typing import Tuple, List, Union

from nkms_eth.agents import NuCypherKMSTokenAgent
from nkms_eth.policies import PolicyArrangement


class TokenActor(ABC):

    def __init__(self, token_agent: NuCypherKMSTokenAgent, address: Union[bytes, str]):
        self.token_agent = token_agent

        if isinstance(address, bytes):
            address = address.hex()
        self.address = address

        self._transactions = OrderedDict()    # Tracks

    def __repr__(self):
        class_name = self.__class__.__name__
        r = "{}(address='{}')"
        r = r.format(class_name, self.address)
        return r

    def eth_balance(self):
        """Return this actors's current ETH balance"""

        balance = self.token_agent._blockchain._chain.web3.eth.getBalance(self.address)
        return balance

    def token_balance(self):
        """Return this actors's current token balance"""

        balance = self.token_agent.get_balance(address=self.address)
        return balance


class Miner(TokenActor):
    """
    Ursula - practically carrying a pickaxe.

    Accepts a running blockchain, deployed token contract, and deployed escrow contract.
    If the provided token and escrow contracts are not deployed,
    ContractDeploymentError will be raised.

    """

    def __init__(self, miner_agent, address):
        super().__init__(token_agent=miner_agent.token_agent, address=address)

        self.miner_agent = miner_agent
        miner_agent.miners.append(self)    # Track Miners

        self.token_agent = miner_agent.token_agent
        self._blockchain = self.token_agent._blockchain


        self._locked_tokens = None
        self._update_locked_tokens()

    def _update_locked_tokens(self) -> None:
        """Query the contract for the amount of locked tokens on this miner's eth address and cache it"""

        self._locked_tokens = self.miner_agent.call().getLockedTokens(self.address)
        return None

    def _approve_escrow(self, amount: int) -> str:
        """Approve the transfer of token from the miner's address to the escrow contract."""

        txhash = self.token_agent.transact({'from': self.address}).approve(self.miner_agent.contract_address, amount)
        self._blockchain.wait_for_receipt(txhash)

        self._transactions[datetime.now()] = txhash

        return txhash

    def _send_tokens_to_escrow(self, amount, locktime) -> str:
        """Send tokes to the escrow from the miner's address"""

        deposit_txhash = self.miner_agent.transact({'from': self.address}).deposit(amount, locktime)
        self._blockchain.wait_for_receipt(deposit_txhash)

        self._transactions[datetime.now()] = deposit_txhash

        return deposit_txhash

    @property
    def is_staking(self, query=True):
        """Checks if this Miner currently has locked tokens."""

        if query:
            self._update_locked_tokens()
        return bool(self._locked_tokens > 0)

    def lock(self, amount: int, locktime: int) -> Tuple[str, str, str]:
        """Public facing method for token locking."""

        approve_txhash = self._approve_escrow(amount=amount)
        deposit_txhash = self._send_tokens_to_escrow(amount=amount, locktime=locktime)

        lock_txhash = self.miner_agent.transact({'from': self.address}).switchLock()
        self._blockchain.wait_for_receipt(lock_txhash)

        self._transactions[datetime.now()] = lock_txhash

        return approve_txhash, deposit_txhash, lock_txhash

    def confirm_activity(self) -> str:
        """Miner rewarded for every confirmed period"""

        txhash = self.miner_agent.transact({'from': self.address}).confirmActivity()
        self._blockchain.wait_for_receipt(txhash)

        self._transactions[datetime.now()] = txhash

        return txhash

    def mint(self) -> str:
        """Computes and transfers tokens to the miner's account"""

        txhash = self.miner_agent.transact({'from': self.address}).mint()
        self._blockchain.wait_for_receipt(txhash)
        self._transactions[datetime.now()] = txhash

        return txhash

    def collect_policy_reward(self, policy_manager) -> str:
        """Collect policy reward in ETH"""

        txhash = policy_manager.transact({'from': self.address}).withdraw()
        self._blockchain.wait_for_receipt(txhash)
        self._transactions[datetime.now()] = txhash

        return txhash

    def publish_miner_id(self, miner_id) -> str:
        """Store a new Miner ID"""

        txhash = self.miner_agent.transact({'from': self.address}).setMinerId(miner_id)
        self._blockchain.wait_for_receipt(txhash)
        self._transactions[datetime.now()] = txhash

        return txhash

    def fetch_miner_ids(self) -> tuple:
        """Retrieve all stored Miner IDs on this miner"""

        count = self.miner_agent.call().getMinerInfo(self.miner_agent._deployer.MinerInfoField.MINER_IDS_LENGTH.value,
                                                     self.address,
                                                     0).encode('latin-1')

        count = self._blockchain._chain.web3.toInt(count)

        miner_ids = list()
        for index in range(count):
            miner_id = self.miner_agent.call().getMinerInfo(self.miner_agent._deployer.MinerInfoField.MINER_ID.value,
                                                            self.address,
                                                            index)
            encoded_miner_id = miner_id.encode('latin-1')  # TODO change when v4 of web3.py is released
            miner_ids.append(encoded_miner_id)

        return tuple(miner_ids)

    def withdraw(self, amount: int=0, entire_balance=False) -> str:
        """Withdraw tokens"""

        if entire_balance and amount:
            raise Exception("Specify an amount or entire balance, not both")

        if entire_balance:
            tokens_amount = self._blockchain._chain.web3.toInt(self.miner_agent.call().getMinerInfo(self.miner_agent._deployer.MinerInfoField.VALUE.value,
                                                               self.address,
                                                               0).encode('latin-1'))

            txhash = self.miner_agent.transact({'from': self.address}).withdraw(tokens_amount)
        else:
            txhash = self.miner_agent.transact({'from': self.address}).withdraw(amount)

        self._blockchain._chain.wait.for_receipt(txhash, timeout=self._blockchain._timeout)

        return txhash


class PolicyAuthor(TokenActor):
    """Alice"""

    def __init__(self, address: bytes, policy_agent):
        super().__init__(token_agent=policy_agent._token, address=address)
        self.policy_agent = policy_agent

        self._arrangements = OrderedDict()    # Track authored policies by id

    def make_arrangement(self, miner: Miner, periods: int, rate: int, arrangement_id: bytes=None) -> 'PolicyArrangement':
        """
        Create a new arrangement to carry out a blockchain policy for the specified rate and time.
        """

        value = rate * periods
        arrangement = PolicyArrangement(author=self,
                                            miner=miner,
                                            value=value,
                                            periods=periods)

        self._arrangements[arrangement.id] = {arrangement_id: arrangement}
        return arrangement

    def get_arrangement(self, arrangement_id: bytes) -> PolicyArrangement:
        """Fetch a published arrangement from the blockchain"""

        blockchain_record = self.policy_agent.call().policies(arrangement_id)
        author_address, miner_address, rate, start_block, end_block, downtime_index = blockchain_record

        duration = end_block - start_block

        miner = Miner(address=miner_address, miner_agent=self.policy_agent.miner_agent)
        arrangement = PolicyArrangement(author=self, miner=miner, periods=duration)

        arrangement.is_published = True
        return arrangement

    def revoke_arrangement(self, arrangement_id):
        """Get the arrangement from the cache and revoke it on the blockchain"""
        try:
            arrangement = self._arrangements[arrangement_id]
        except KeyError:
            raise Exception('No such arrangement')  #TODO
        else:
            txhash = arrangement.revoke()
        return txhash

    def recruit(self, quantity: int) -> List[str]:
        """Uses sampling logic to gather miner address from the blockchain"""

        miner_addresses = self.policy_agent.miner_agent.sample(quantity=quantity)
        return miner_addresses

    def balance(self):
        """Get the balance of this actor's address"""
        return self.policy_agent.miner_agent.call().balanceOf(self.address)

