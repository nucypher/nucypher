from abc import ABC
from collections import OrderedDict
from datetime import datetime
from typing import Tuple, List, Union

from nucypher.blockchain.eth.agents import NuCypherTokenAgent


class TokenActor(ABC):

    class ActorError(Exception):
        pass

    def __init__(self, token_agent: NuCypherTokenAgent, address: Union[bytes, str]):
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

        self.__locked_tokens = self.miner_agent.contract.functions.getLockedTokens(self.address).call()

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

        txhash = self.token_agent.contract.functions.approve(self.miner_agent.contract_address, amount).transact({'from': self.address})
        self.blockchain.wait_for_receipt(txhash)

        self._transactions.append((datetime.utcnow(), txhash))

        return txhash

    def _send_tokens_to_escrow(self, amount, periods) -> str:
        """Send tokes to the escrow from the miner's address"""

        deposit_txhash = self.miner_agent.contract.functions.deposit(amount, periods).transact({'from': self.address})

        self.blockchain.wait_for_receipt(deposit_txhash)

        self._transactions.append((datetime.utcnow(), deposit_txhash))

        return deposit_txhash

    def deposit(self, amount: int, periods: int) -> Tuple[str, str]:
        """Public facing method for token locking."""
        approve_txhash = self._approve_escrow(amount=amount)
        deposit_txhash = self._send_tokens_to_escrow(amount=amount, periods=periods)

        return approve_txhash, deposit_txhash

    # TODO add divide_stake method
    def switch_lock(self):
        lock_txhash = self.miner_agent.contract.functions.switchLock().transact({'from': self.address})
        self.blockchain.wait_for_receipt(lock_txhash)

        self._transactions.append((datetime.utcnow(), lock_txhash))
        return lock_txhash

    def confirm_activity(self) -> str:
        """Miner rewarded for every confirmed period"""

        txhash = self.miner_agent.contract.functions.confirmActivity().transact({'from': self.address})
        self.blockchain.wait_for_receipt(txhash)

        self._transactions.append((datetime.utcnow(), txhash))

        return txhash

    def mint(self) -> Tuple[str, str]:
        """Computes and transfers tokens to the miner's account"""

        mint_txhash = self.miner_agent.contract.functions.mint().transact({'from': self.address})

        self.blockchain.wait_for_receipt(mint_txhash)
        self._transactions.append((datetime.utcnow(), mint_txhash))

        return mint_txhash

    def collect_policy_reward(self, policy_manager):
        """Collect rewarded ETH"""

        policy_reward_txhash = policy_manager.contract.functions.withdraw().transact({'from': self.address})
        self.blockchain.wait_for_receipt(policy_reward_txhash)

        self._transactions.append((datetime.utcnow(), policy_reward_txhash))

        return policy_reward_txhash

    def collect_staking_reward(self) -> str:
        """Withdraw tokens rewarded for staking."""

        token_amount_bytes = self.miner_agent.contract.functions.getMinerInfo(self.miner_agent.MinerInfo.VALUE.value,
                                                                  self.address, 0).call()

        token_amount = self.blockchain._chain.web3.toInt(token_amount_bytes)

        # reward_amount = TODO

        reward_txhash = self.miner_agent.contract.functions.withdraw(token_amount).transact({'from': self.address})

    def __validate_stake(self, amount: int, periods: int) -> bool:

        assert self.miner_agent.validate_stake_amount(amount=amount)
        assert self.miner_agent.validate_locktime(periods=periods)

        if not self.token_balance() >= amount:
            raise self.StakingError("Insufficient miner token balance ({balance})".format(balance=self.token_balance()))
        else:
            return True

    def stake(self, amount, locktime, entire_balance=False):
        """
        High level staking method for Miners.
        """

        staking_transactions = OrderedDict()  # Time series of txhases

        if entire_balance and amount:
            raise self.StakingError("Specify an amount or entire balance, not both")

        if entire_balance is True:
            balance_bytes = self.miner_agent.contract.functions.getMinerInfo(self.miner_agent.MinerInfo.VALUE.value,
                                                                             self.address, 0).call()
            amount = self.blockchain._chain.web3.toInt(balance_bytes)

        assert self.__validate_stake(amount=amount, periods=periods)

        approve_txhash, initial_deposit_txhash = self.deposit(amount=amount, periods=periods)
        self._transactions.append((datetime.utcnow(), initial_deposit_txhash))

        return staking_transactions

    def publish_data(self, data) -> str:
        """Store new data"""

        txhash = self.miner_agent.contract.functions.setMinerId(data).transact({'from': self.address})
        self.blockchain.wait_for_receipt(txhash)

        self._transactions.append((datetime.utcnow(), txhash))

        return txhash

    def fetch_data(self) -> tuple:
        """Retrieve all asosciated contract data for this miner."""

        count_bytes = self.miner_agent.contract.functions.getMinerInfo(self.miner_agent.MinerInfo.MINER_IDS_LENGTH.value,
                                                           self.address, 0).call()

        count = self.blockchain._chain.web3.toInt(count_bytes)

        miner_ids = list()
        for index in range(count):
            miner_id = self.miner_agent.contract.functions.getMinerInfo(self.miner_agent.MinerInfo.MINER_ID.value,
                                                            self.address, index).call()
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

