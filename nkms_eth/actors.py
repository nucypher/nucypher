from abc import ABC
from collections import OrderedDict
from datetime import datetime
from typing import Tuple, List, Union

from nkms_eth.agents import NuCypherKMSTokenAgent


class TokenActor(ABC):

    class ActorError(Exception):
        pass

    def __init__(self, token_agent: NuCypherKMSTokenAgent, address: Union[bytes, str]):
        self.token_agent = token_agent

        if isinstance(address, bytes):
            address = address.hex()
        self.address = address

        self._transactions = list()

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

        self.__locked_tokens = None
        self.__update_locked_tokens()

    def __update_locked_tokens(self) -> None:
        """Query the contract for the amount of locked tokens on this miner's eth address and cache it"""

        self.__locked_tokens = self.miner_agent.read().getLockedTokens(self.address)

    @property
    def is_staking(self):
        """Checks if this Miner currently has locked tokens."""

        self.__update_locked_tokens()
        return bool(self.__locked_tokens > 0)

    @property
    def locked_tokens(self,):
        """Returns the amount of tokens this miner has locked."""

        self.__update_locked_tokens()
        return self.__locked_tokens

    def _approve_escrow(self, amount: int) -> str:
        """Approve the transfer of token from the miner's address to the escrow contract."""

        txhash = self.token_agent.transact({'from': self.address}).approve(self.miner_agent.contract_address, amount)
        self.blockchain.wait_for_receipt(txhash)

        self._transactions.append((datetime.utcnow(), txhash))

        return txhash

    def _send_tokens_to_escrow(self, amount, locktime) -> str:
        """Send tokes to the escrow from the miner's address"""

        deposit_txhash = self.miner_agent.transact({'from': self.address}).deposit(amount, locktime)
        self.blockchain.wait_for_receipt(deposit_txhash)

        self._transactions.append((datetime.utcnow(), deposit_txhash))

        return deposit_txhash

    def deposit(self, amount: int, locktime: int) -> Tuple[str, str]:
        """Public facing method for token locking."""
        approve_txhash = self._approve_escrow(amount=amount)
        deposit_txhash = self._send_tokens_to_escrow(amount=amount, locktime=locktime)

        return approve_txhash, deposit_txhash

    def switch_lock(self):
        lock_txhash = self.miner_agent.transact({'from': self.address}).switchLock()
        self.blockchain.wait_for_receipt(lock_txhash)

        self._transactions.append((datetime.utcnow(), lock_txhash))
        return lock_txhash

    def _confirm_activity(self) -> str:
        """Miner rewarded for every confirmed period"""

        txhash = self.miner_agent.transact({'from': self.address}).confirmActivity()
        self.blockchain.wait_for_receipt(txhash)

        self._transactions.append((datetime.utcnow(), txhash))

        return txhash

    def mint(self) -> Tuple[str, str]:
        """Computes and transfers tokens to the miner's account"""

        confirm_txhash = self.miner_agent.transact({'from': self.address, 'gas_price': 0}).confirmActivity()
        mint_txhash = self.miner_agent.transact({'from': self.address, 'gas_price': 0}).mint()

        self.blockchain.wait_for_receipt(mint_txhash)
        self._transactions.append((datetime.utcnow(), mint_txhash))

        return confirm_txhash, mint_txhash

    def collect_policy_reward(self, policy_manager):
        """Collect rewarded ETH"""

        policy_reward_txhash = policy_manager.transact({'from': self.address}).withdraw()
        self.blockchain.wait_for_receipt(policy_reward_txhash)

        self._transactions.append((datetime.utcnow(), policy_reward_txhash))

        return policy_reward_txhash

    def collect_staking_reward(self) -> str:
        """Withdraw tokens rewarded for staking."""

        token_amount_bytes = self.miner_agent.read().getMinerInfo(self.miner_agent.MinerInfo.VALUE.value,
                                                                  self.address,
                                                                  0).encode('latin-1')

        token_amount = self.blockchain._chain.web3.toInt(token_amount_bytes)

        # reward_amount = TODO

        reward_txhash = self.miner_agent.transact({'from': self.address}).withdraw(token_amount)

        self.blockchain.wait_for_receipt(reward_txhash)
        self._transactions.append((datetime.utcnow(), reward_txhash))

        return reward_txhash

    def stake(self, amount, locktime, entire_balance=False, auto_switch_lock=False):
        """
        High level staking method for Miners.
        """

        staking_transactions = OrderedDict()  # Time series of txhases

        if entire_balance and amount:
            raise self.StakingError("Specify an amount or entire balance, not both")

        if not locktime >= 0:
            min_stake_time = self.miner_agent._deployer._min_release_periods
            raise self.StakingError('Locktime must be at least {}'.format(min_stake_time))

        if entire_balance is True:
            balance_bytes = self.miner_agent.read().getMinerInfo(self.miner_agent.MinerInfo.VALUE.value,
                                                                 self.address,
                                                                 0).encode('latin-1')

            amount = self.blockchain._chain.web3.toInt(balance_bytes)
        else:
            if not amount > 0:
                raise self.StakingError('Staking amount must be greater than zero.')

        approve_txhash, initial_deposit_txhash = self.deposit(amount=amount, locktime=locktime)
        self._transactions.append((datetime.utcnow(), initial_deposit_txhash))

        if auto_switch_lock is True:
            lock_txhash = self.switch_lock()
            self._transactions.append((datetime.utcnow(), lock_txhash))

        return staking_transactions

    def publish_data(self, data) -> str:
        """Store new data"""

        txhash = self.miner_agent.transact({'from': self.address}).setMinerId(data)
        self.blockchain.wait_for_receipt(txhash)

        self._transactions.append((datetime.utcnow(), txhash))

        return txhash

    def fetch_data(self) -> tuple:
        """Retrieve all asosciated contract data for this miner."""

        count_bytes = self.miner_agent.read().getMinerInfo(self.miner_agent.MinerInfo.MINER_IDS_LENGTH.value,
                                                           self.address,
                                                           0).encode('latin-1')  # TODO change when v4 of web3.py is released

        count = self.blockchain._chain.web3.toInt(count_bytes)

        miner_ids = list()
        for index in range(count):
            miner_id = self.miner_agent.read().getMinerInfo(self.miner_agent.MinerInfo.MINER_ID.value,
                                                            self.address,
                                                            index)
            encoded_miner_id = miner_id.encode('latin-1')
            miner_ids.append(encoded_miner_id)

        return tuple(miner_ids)


class PolicyAuthor(TokenActor):
    """Alice"""

    def __init__(self, address: bytes, policy_agent):
        super().__init__(token_agent=policy_agent._token, address=address)
        self.policy_agent = policy_agent

        self._arrangements = OrderedDict()    # Track authored policies by id

    def revoke_arrangement(self, arrangement_id):
        """Get the arrangement from the cache and revoke it on the blockchain"""
        try:
            arrangement = self._arrangements[arrangement_id]
        except KeyError:
            raise self.ActorError('No such arrangement')
        else:
            txhash = arrangement.revoke()
        return txhash

    def recruit(self, quantity: int) -> List[str]:
        """Uses sampling logic to gather miner address from the blockchain"""

        miner_addresses = self.policy_agent.miner_agent.sample(quantity=quantity)
        return miner_addresses

