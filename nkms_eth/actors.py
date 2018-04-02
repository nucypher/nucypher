from abc import ABC
from collections import OrderedDict
from datetime import datetime
from typing import Tuple, List, Union

from nkms_eth.agents import NuCypherKMSTokenAgent
from nkms_eth.policies import BlockchainArrangement


class TokenActor(ABC):

    class ActorError(Exception):
        pass

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

        balance = self.token_agent.blockchain._chain.web3.eth.getBalance(self.address)
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

    class StakingError(TokenActor.ActorError):
        pass

    def __init__(self, miner_agent, address):
        super().__init__(token_agent=miner_agent.token_agent, address=address)

        self.miner_agent = miner_agent
        miner_agent.miners.append(self)    # Track Miners

        self.token_agent = miner_agent.token_agent
        self.blockchain = self.token_agent.blockchain

        self._locked_tokens = None
        self._update_locked_tokens()

    def _update_locked_tokens(self) -> None:
        """Query the contract for the amount of locked tokens on this miner's eth address and cache it"""

        self._locked_tokens = self.miner_agent.read().getLockedTokens(self.address)
        return None

    @property
    def is_staking(self, query=True):
        """Checks if this Miner currently has locked tokens."""

        if query:
            self._update_locked_tokens()
        return bool(self._locked_tokens > 0)

    def _approve_escrow(self, amount: int) -> str:
        """Approve the transfer of token from the miner's address to the escrow contract."""

        txhash = self.token_agent.transact({'from': self.address}).approve(self.miner_agent.contract_address, amount)
        self.blockchain.wait_for_receipt(txhash)

        self._transactions[datetime.utcnow()] = txhash

        return txhash

    def _send_tokens_to_escrow(self, amount, locktime) -> str:
        """Send tokes to the escrow from the miner's address"""

        deposit_txhash = self.miner_agent.transact({'from': self.address}).deposit(amount, locktime)
        self.blockchain.wait_for_receipt(deposit_txhash)

        self._transactions[datetime.utcnow()] = deposit_txhash

        return deposit_txhash

    def deposit(self, amount: int, locktime: int) -> Tuple[str, str]:
        """Public facing method for token locking."""

        approve_txhash = self._approve_escrow(amount=amount)
        deposit_txhash = self._send_tokens_to_escrow(amount=amount, locktime=locktime)

        return approve_txhash, deposit_txhash

    def switch_lock(self):
        lock_txhash = self.miner_agent.transact({'from': self.address}).switchLock()
        self.blockchain.wait_for_receipt(lock_txhash)

        self._transactions[datetime.utcnow()] = lock_txhash
        return lock_txhash

    def lock(self, amount: int, locktime: int) -> Tuple[str, str, str]:
        """Public facing method for token locking."""

        approve_txhash, deposit_txhash = self.deposit(amount=amount, locktime=locktime)
        lock_txhash = self.switch_lock()

        return approve_txhash, deposit_txhash, lock_txhash

    def confirm_activity(self) -> str:
        """Miner rewarded for every confirmed period"""

        txhash = self.miner_agent.transact({'from': self.address}).confirmActivity()
        self.blockchain.wait_for_receipt(txhash)

        self._transactions[datetime.utcnow()] = txhash

        return txhash

    def mint(self) -> str:
        """Computes and transfers tokens to the miner's account"""

        txhash = self.miner_agent.transact({'from': self.address}).mint()
        self.blockchain.wait_for_receipt(txhash)
        self._transactions[datetime.utcnow()] = txhash

        return txhash

    def collect_reward(self, policy_manager) -> str:
        """Collect policy reward in ETH"""

        txhash = policy_manager.transact({'from': self.address}).withdraw()  # TODO: Calculate reward
        self.blockchain.wait_for_receipt(txhash)
        self._transactions[datetime.utcnow()] = txhash

        return txhash

    # TODO
    # def withdraw(self, amount: int=0, entire_balance=False) -> str:
    #     """Withdraw tokens"""
    #
    #
    #     if entire_balance and amount:
    #         raise Exception("Specify an amount or entire balance, not both")
    #
    #     if entire_balance:
    #         tokens_amount = self._blockchain._chain.web3.toInt(self.miner_agent.read().getMinerInfo(self.miner_agent._deployer.MinerInfoField.VALUE.value,
    #                                                            self.address,
    #                                                            0).encode('latin-1'))
    #
    #         txhash = self.miner_agent.transact({'from': self.address}).withdraw(tokens_amount)
    #     else:
    #         txhash = self.miner_agent.transact({'from': self.address}).withdraw(amount)
    #
    #     self._blockchain._chain.wait.for_receipt(txhash)
    #
    #     return txhash

    def stake(self, amount, locktime, entire_balance=False, restake=False, auto_switch_lock=False):
        """
        High level staking method for Miners.
        """
        staking_transactions = OrderedDict()  # Time series of txhases

        if entire_balance and amount:
            raise self.StakingError("Specify an amount or entire balance, not both")

        if not locktime >= self.miner_agent._deployer._min_release_periods:
            raise self.StakingError('Locktime must be at least {}'.format(self.miner_agent._deployer._min_release_periods))

        if entire_balance is True:
            balance_bytes = self.miner_agent.read().getMinerInfo(self.miner_agent._deployer.MinerInfoField.VALUE.value,
                                                                 self.address,
                                                                 0).encode('latin-1')

            amount = self.blockchain._chain.web3.toInt(balance_bytes)
        else:
            if not amount > 0:
                raise self.StakingError('Staking amount must be greater than zero.')

        approve_txhash, initial_deposit_txhash = self.deposit(amount=amount, locktime=locktime)
        staking_transactions[datetime.utcnow()] = initial_deposit_txhash

        if auto_switch_lock is True:
            lock_txhash = self.switch_lock()
            staking_transactions[datetime.utcnow()] = lock_txhash

        # not_time_yet = True    # TODO
        # while not_time_yet:

            # self.blockchain.wait_time(wait_hours=1)

            # confirm_txhash = self.confirm_activity()
            # staking_transactions[datetime.utcnow()] = confirm_txhash

            # mint_txhash = self.mint()
            # staking_transactions[datetime.utcnow()] = mint_txhash

            # if restake is True:
            #     #TODO: get reward amount
            #     self.collect_reward()
            #     self.deposit()

        return staking_transactions

    #TODO: Sidechain datastore
    # def publish_data(self, miner_id) -> str:
    #     """Store a new Miner ID"""
    #
    #     txhash = self.miner_agent.transact({'from': self.address}).setMinerId(miner_id)
    #     self._blockchain.wait_for_receipt(txhash)
    #     self._transactions[datetime.utcnow()] = txhash
    #
    #     return txhash
    #
    # def fetch_miner_data(self) -> tuple:
    #     """Retrieve all stored Miner IDs on this miner"""
    #
    #     count = self.miner_agent.read().getMinerInfo(self.miner_agent._deployer.MinerInfoField.MINER_IDS_LENGTH.value,
    #                                                  self.address,
    #                                                  0).encode('latin-1')
    #
    #     count = self._blockchain._chain.web3.toInt(count)
    #
    #     miner_ids = list()
    #     for index in range(count):
    #         miner_id = self.miner_agent.read().getMinerInfo(self.miner_agent._deployer.MinerInfoField.MINER_ID.value,
    #                                                         self.address,
    #                                                         index)
    #         encoded_miner_id = miner_id.encode('latin-1')  # TODO change when v4 of web3.py is released
    #         miner_ids.append(encoded_miner_id)
    #
    #     return tuple(miner_ids)


class PolicyAuthor(TokenActor):
    """Alice"""

    def __init__(self, address: bytes, policy_agent):
        super().__init__(token_agent=policy_agent._token, address=address)
        self.policy_agent = policy_agent

        self._arrangements = OrderedDict()    # Track authored policies by id

    def make_arrangement(self, miner: Miner, periods: int, rate: int, arrangement_id: bytes=None) -> 'BlockchainArrangement':
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

