from collections import OrderedDict
from datetime import datetime
from typing import Tuple, List, Union

from nucypher.blockchain.eth.agents import NucypherTokenAgent, MinerAgent, PolicyAgent


class NucypherTokenActor:

    class ActorError(Exception):
        pass

    def __init__(self, address: Union[str, bytes], token_agent: NucypherTokenAgent=None, *args, **kwargs):

        if token_agent is None:
            token_agent = NucypherTokenAgent()
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
        balance = self.token_agent.blockchain.interface.w3.eth.getBalance(self.address)
        return balance

    def token_balance(self):
        """Return this actors's current token balance"""
        balance = self.token_agent.get_balance(address=self.address)
        return balance


class Miner(NucypherTokenActor):
    """
    Ursula - practically carrying a pickaxe.
    """

    class StakingError(NucypherTokenActor.ActorError):
        pass

    def __init__(self, miner_agent: MinerAgent=None, *args, **kwargs):
        if miner_agent is None:
            miner_agent = MinerAgent(token_agent=NucypherTokenAgent())
        super().__init__(token_agent=miner_agent.token_agent, *args, **kwargs)

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

    def _send_tokens_to_escrow(self, amount, lock_periods) -> str:
        """Send tokes to the escrow from the miner's address"""

        deposit_txhash = self.miner_agent.contract.functions.deposit(amount, lock_periods).transact({'from': self.address})

        self.blockchain.wait_for_receipt(deposit_txhash)

        self._transactions.append((datetime.utcnow(), deposit_txhash))

        return deposit_txhash

    def deposit(self, amount: int, lock_periods: int) -> Tuple[str, str]:
        """Public facing method for token locking."""
        approve_txhash = self._approve_escrow(amount=amount)
        deposit_txhash = self._send_tokens_to_escrow(amount=amount, lock_periods=lock_periods)

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

        token_amount = self.miner_agent.contract.functions.minerInfo(self.address).call()[0]
        staked_amount = max(self.miner_agent.contract.functions.getLockedTokens(self.address).call(),
                            self.miner_agent.contract.functions.getLockedTokens(self.address, 1).call())

        collection_txhash = self.miner_agent.contract.functions.withdraw(token_amount - staked_amount).transact({'from': self.address})

        self.blockchain.wait_for_receipt(collection_txhash)
        self._transactions.append((datetime.utcnow(), collection_txhash))

        return collection_txhash

    def __validate_stake(self, amount: int, lock_periods: int) -> bool:

        assert self.miner_agent.validate_stake_amount(amount=amount)
        assert self.miner_agent.validate_locktime(lock_periods=lock_periods)

        if not self.token_balance() >= amount:
            raise self.StakingError("Insufficient miner token balance ({balance})".format(balance=self.token_balance()))
        else:
            return True

    def stake(self, amount, lock_periods, entire_balance=False):
        """
        High level staking method for Miners.
        """

        staking_transactions = OrderedDict()  # Time series of txhases

        if entire_balance and amount:
            raise self.StakingError("Specify an amount or entire balance, not both")

        if entire_balance is True:
            amount = self.miner_agent.contract.functions.getMinerInfo(self.miner_agent.MinerInfo.VALUE.value,
                                                                       self.address, 0).call()
        amount = self.blockchain.interface.w3.toInt(amount)

        assert self.__validate_stake(amount=amount, lock_periods=lock_periods)

        approve_txhash, initial_deposit_txhash = self.deposit(amount=amount, lock_periods=lock_periods)
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

        count_bytes = self.miner_agent.contract.functions.getMinerIdsLength(self.address).call()

        count = self.blockchain.interface.w3.toInt(count_bytes)

        miner_ids = list()
        for index in range(count):
            miner_id = self.miner_agent.contract.functions.getMinerId(self.address, index).call()
            miner_ids.append(miner_id)
        return tuple(miner_ids)


class PolicyAuthor(NucypherTokenActor):
    """Alice"""

    def __init__(self, policy_agent: PolicyAgent=None, *args, **kwargs):

        if policy_agent is None:
            # all defaults
            token_agent = NucypherTokenAgent()
            miner_agent = MinerAgent(token_agent=token_agent)
            policy_agent = PolicyAgent(miner_agent=miner_agent)

        self.policy_agent = policy_agent
        super().__init__(token_agent=self.policy_agent.token_agent, *args, **kwargs)

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

