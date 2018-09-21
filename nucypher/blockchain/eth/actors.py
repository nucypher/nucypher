from collections import OrderedDict
from datetime import datetime
from typing import Tuple, List

import maya

from nucypher.blockchain.eth.agents import NucypherTokenAgent, MinerAgent, PolicyAgent
from nucypher.blockchain.eth.constants import calculate_period_duration, datetime_to_period, validate_stake_amount
from nucypher.blockchain.eth.interfaces import EthereumContractRegistry


def only_me(func):
    def wrapped(actor=None, *args, **kwargs):
        if not actor.is_me:
            raise actor.MinerError("You are not {}".format(actor.__class.__.__name__))
        return func(actor, *args, **kwargs)
    return wrapped


class NucypherTokenActor:
    """
    Concrete base class for any actor that will interface with NuCypher's ethereum smart contracts.
    """

    class ActorError(Exception):
        pass

    def __init__(self,
                 checksum_address: str = None,
                 token_agent: NucypherTokenAgent = None,
                 registry_filepath: str = None) -> None:
        """
        :param checksum_address:  If not passed, we assume this is an unknown actor

        :param token_agent:  The token agent with the blockchain attached; If not passed, A default
        token agent and blockchain connection will be created from default values.

        """
        try:
            parent_address = self.checksum_public_address  # type: str
            if checksum_address is not None:
                if parent_address != checksum_address:
                    raise ValueError("Can't have two different addresses.")
        except AttributeError:
            self.checksum_public_address = checksum_address

        if registry_filepath is not None:
            EthereumContractRegistry(registry_filepath=registry_filepath)

        self.token_agent = token_agent if token_agent is not None else NucypherTokenAgent()
        self._transaction_cache = list()  # track transactions transmitted

    def __repr__(self):
        class_name = self.__class__.__name__
        r = "{}(address='{}')"
        r = r.format(class_name, self.checksum_public_address)
        return r

    @property
    def eth_balance(self):
        """Return this actors's current ETH balance"""
        balance = self.token_agent.blockchain.interface.w3.eth.getBalance(self.checksum_public_address)
        return balance

    @property
    def token_balance(self):
        """Return this actors's current token balance"""
        balance = self.token_agent.get_balance(address=self.checksum_public_address)
        return balance


class Miner(NucypherTokenActor):
    """
    Ursula baseclass for blockchain operations, practically carrying a pickaxe.
    """

    class MinerError(NucypherTokenActor.ActorError):
        pass

    def __init__(self,
                 is_me=True,
                 miner_agent: MinerAgent = None,
                 *args, **kwargs) -> None:

        miner_agent = miner_agent if miner_agent is not None else MinerAgent()
        super().__init__(token_agent=miner_agent.token_agent, *args, **kwargs)

        # Extrapolate dependencies
        self.miner_agent = miner_agent
        self.token_agent = miner_agent.token_agent
        self.blockchain = self.token_agent.blockchain

        # Establish initial state
        self.is_me = is_me
    #
    # Staking
    #
    @property
    def is_staking(self):
        """Checks if this Miner currently has locked tokens."""
        return bool(self.locked_tokens > 0)

    @property
    def locked_tokens(self, ):
        """Returns the amount of tokens this miner has locked."""
        return self.miner_agent.get_locked_tokens(node_address=self.checksum_public_address)

    @property
    def stakes(self) -> Tuple[list]:
        """Read all live stake data from the blockchain and return it as a tuple"""
        stakes_reader = self.miner_agent.get_all_stakes(miner_address=self.checksum_public_address)
        return tuple(stakes_reader)

    @only_me
    def deposit(self, amount: int, lock_periods: int) -> Tuple[str, str]:
        """Public facing method for token locking."""
        if not self.is_me:
            raise self.MinerError("Cannot execute miner staking functions with a non-self Miner instance.")

        approve_txhash = self.token_agent.approve_transfer(amount=amount,
                                                           target_address=self.miner_agent.contract_address,
                                                           sender_address=self.checksum_public_address)

        deposit_txhash = self.miner_agent.deposit_tokens(amount=amount,
                                                         lock_periods=lock_periods,
                                                         sender_address=self.checksum_public_address)

        return approve_txhash, deposit_txhash

    @only_me
    def divide_stake(self, stake_index: int, target_value: int,
                     additional_periods: int = None, expiration: maya.MayaDT = None) -> dict:
        """
        Modifies the unlocking schedule and value of already locked tokens.

        This actor requires that is_me is True, and that the expiration datetime is after the existing
        locking schedule of this miner, or an exception will be raised.

        :param target_value:  The quantity of tokens in the smallest denomination.
        :param expiration: The new expiration date to set.
        :return: Returns the blockchain transaction hash

        """

        if additional_periods and expiration:
            raise ValueError("Pass the number of lock periods or an expiration MayaDT; not both.")

        _first_period, last_period, locked_value = self.miner_agent.get_stake_info(
            miner_address=self.checksum_public_address, stake_index=stake_index)
        if expiration:
            additional_periods = datetime_to_period(datetime=expiration) - last_period

            if additional_periods <= 0:
                raise self.MinerError("Expiration {} must be at least 1 period from now.".format(expiration))

        if target_value >= locked_value:
            raise self.MinerError("Cannot divide stake; Value must be less than the specified stake value.")

        # Ensure both halves are for valid amounts
        validate_stake_amount(amount=target_value)
        validate_stake_amount(amount=locked_value - target_value)

        tx = self.miner_agent.divide_stake(miner_address=self.checksum_public_address,
                                           stake_index=stake_index,
                                           target_value=target_value,
                                           periods=additional_periods)

        self.blockchain.wait_for_receipt(tx)
        return tx

    @only_me
    def __validate_stake(self, amount: int, lock_periods: int) -> bool:

        from .constants import validate_locktime, validate_stake_amount
        assert validate_stake_amount(amount=amount)
        assert validate_locktime(lock_periods=lock_periods)

        if not self.token_balance >= amount:
            raise self.MinerError("Insufficient miner token balance ({balance})".format(balance=self.token_balance))
        else:
            return True

    @only_me
    def initialize_stake(self,
                         amount: int,
                         lock_periods: int = None,
                         expiration: maya.MayaDT = None,
                         entire_balance: bool = False) -> dict:
        """
        High level staking method for Miners.

        :param amount: Amount of tokens to stake denominated in the smallest unit.
        :param lock_periods: Duration of stake in periods.
        :param expiration: A MayaDT object representing the time the stake expires; used to calculate lock_periods.
        :param entire_balance: If True, stake the entire balance of this node, or the maximum possible.

        """

        if lock_periods and expiration:
            raise ValueError("Pass the number of lock periods or an expiration MayaDT; not both.")
        if entire_balance and amount:
            raise self.MinerError("Specify an amount or entire balance, not both")

        if expiration:
            lock_periods = calculate_period_duration(future_time=expiration)
        if entire_balance is True:
            amount = self.token_balance

        staking_transactions = OrderedDict()  # type: OrderedDict # Time series of txhases

        # Validate
        assert self.__validate_stake(amount=amount, lock_periods=lock_periods)

        # Transact
        approve_txhash, initial_deposit_txhash = self.deposit(amount=amount, lock_periods=lock_periods)
        self._transaction_cache.append((datetime.utcnow(), initial_deposit_txhash))

        return staking_transactions

    #
    # Reward and Collection
    #

    @only_me
    def confirm_activity(self) -> str:
        """Miner rewarded for every confirmed period"""

        txhash = self.miner_agent.confirm_activity(node_address=self.checksum_public_address)
        self._transaction_cache.append((datetime.utcnow(), txhash))

        return txhash

    @only_me
    def mint(self) -> Tuple[str, str]:
        """Computes and transfers tokens to the miner's account"""

        mint_txhash = self.miner_agent.mint(node_address=self.checksum_public_address)
        self._transaction_cache.append((datetime.utcnow(), mint_txhash))

        return mint_txhash

    @only_me
    def collect_policy_reward(self, policy_manager):
        """Collect rewarded ETH"""

        policy_reward_txhash = policy_manager.collect_policy_reward(collector_address=self.checksum_public_address)
        self._transaction_cache.append((datetime.utcnow(), policy_reward_txhash))

        return policy_reward_txhash

    @only_me
    def collect_staking_reward(self) -> str:
        """Withdraw tokens rewarded for staking."""

        collection_txhash = self.miner_agent.collect_staking_reward(collector_address=self.checksum_public_address)
        self._transaction_cache.append((datetime.utcnow(), collection_txhash))

        return collection_txhash


class PolicyAuthor(NucypherTokenActor):
    """Alice base class for blockchain operations, mocking up new policies!"""

    def __init__(self, checksum_address: str, policy_agent: PolicyAgent = None) -> None:
        """
        :param policy_agent: A policy agent with the blockchain attached; If not passed, A default policy
        agent and blockchain connection will be created from default values.

        """

        if policy_agent is None:
            # From defaults
            self.miner_agent = MinerAgent(token_agent=self.token_agent)
            self.policy_agent = PolicyAgent(miner_agent=self.miner_agent)
        else:
            # From agent
            self.policy_agent = policy_agent
            self.miner_agent = policy_agent.miner_agent

        super().__init__(token_agent=self.policy_agent.token_agent,
                         checksum_address=checksum_address,
                         )

    def recruit(self, quantity: int, **options) -> List[str]:
        """
        Uses sampling logic to gather miners from the blockchain and
        caches the resulting node ethereum addresses.

        :param quantity: Number of ursulas to sample from the blockchain.
        :return: None; Since it only mutates self

        """

        miner_addresses = self.policy_agent.miner_agent.sample(quantity=quantity, **options)
        return miner_addresses

    def create_policy(self, *args, **kwargs):
        """
        Hence the name, a PolicyAuthor can create
        a BlockchainPolicy with themself as the author.

        :return: Returns a newly authored BlockchainPolicy with n proposed arrangements.

        """

        from nucypher.blockchain.eth.policies import BlockchainPolicy
        blockchain_policy = BlockchainPolicy(author=self, *args, **kwargs)
        return blockchain_policy
