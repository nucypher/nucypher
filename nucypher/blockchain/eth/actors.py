import itertools
import math
from collections import OrderedDict
from datetime import datetime
from typing import Tuple

import maya
from constant_sorrow import constants

from nucypher.blockchain.eth.agents import NucypherTokenAgent, MinerAgent, PolicyAgent
from nucypher.blockchain.eth.constants import calculate_period_duration, datetime_to_period, validate_stake_amount


class NucypherTokenActor:
    """
    Concrete base class for any actor that will interface with NuCypher's ethereum smart contracts.
    """

    class ActorError(Exception):
        pass

    def __init__(self, ether_address: str=None, token_agent: NucypherTokenAgent=None, *args, **kwargs):
        """
        :param ether_address:  If not passed, we assume this is an unknown actor

        :param token_agent:  The token agent with the blockchain attached; If not passed, A default
        token agent and blockchain connection will be created from default values.

        """

        # Auto-connect, if needed
        self.token_agent = token_agent if token_agent is not None else NucypherTokenAgent()

        self.ether_address = ether_address if ether_address is not None else constants.UNKNOWN_ACTOR
        self._transaction_cache = list()  # track transactions transmitted

    def __repr__(self):
        class_name = self.__class__.__name__
        r = "{}(address='{}')"
        r = r.format(class_name, self.ether_address)
        return r

    @classmethod
    def from_config(cls, config):
        """Read actor data from a configuration file, and create an actor instance."""
        raise NotImplementedError

    @property
    def eth_balance(self):
        """Return this actors's current ETH balance"""
        balance = self.token_agent.blockchain.interface.w3.eth.getBalance(self.ether_address)
        return balance

    @property
    def token_balance(self):
        """Return this actors's current token balance"""
        balance = self.token_agent.get_balance(address=self.ether_address)
        return balance


class Miner(NucypherTokenActor):
    """
    Ursula baseclass for blockchain operations, practically carrying a pickaxe.
    """

    class MinerError(NucypherTokenActor.ActorError):
        pass

    def __init__(self, is_me=True, miner_agent: MinerAgent=None, *args, **kwargs):
        miner_agent = miner_agent if miner_agent is not None else MinerAgent()
        super().__init__(token_agent=miner_agent.token_agent, *args, **kwargs)

        # Extrapolate dependencies
        self.miner_agent = miner_agent
        self.token_agent = miner_agent.token_agent
        self.blockchain = self.token_agent.blockchain

        # Establish initial state
        self.is_me = is_me
        if self.ether_address is not constants.UNKNOWN_ACTOR:
            node_datastore = self.miner_agent._fetch_node_datastore(node_address=self.ether_address)
        else:
            node_datastore = constants.CONTRACT_DATASTORE_UNAVAILIBLE
        self.__node_datastore = node_datastore

    @classmethod
    def from_config(cls, blockchain_config) -> 'Miner':
        """Read miner data from a configuration file, and create an miner instance."""

        # Use BlockchainConfig to default to the first wallet address
        wallet_address = blockchain_config.wallet_addresses[0]

        instance = cls(ether_address=wallet_address)
        return instance

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
        return self.miner_agent.get_locked_tokens(node_address=self.ether_address)

    @property
    def stakes(self):
        stakes_reader = self.miner_agent.get_all_stakes(miner_address=self.ether_address)
        return stakes_reader

    def deposit(self, amount: int, lock_periods: int) -> Tuple[str, str]:
        """Public facing method for token locking."""
        if not self.is_me:
            raise self.MinerError("Cannot execute miner staking functions with a non-self Miner instance.")

        approve_txhash = self.token_agent.approve_transfer(amount=amount,
                                                           target_address=self.miner_agent.contract_address,
                                                           sender_address=self.ether_address)

        deposit_txhash = self.miner_agent.deposit_tokens(amount=amount,
                                                         lock_periods=lock_periods,
                                                         sender_address=self.ether_address)

        return approve_txhash, deposit_txhash

    def divide_stake(self, stake_index: int, target_value: int,
                     additional_periods: int=None, expiration: maya.MayaDT=None) -> dict:
        """
        Modifies the unlocking schedule and value of already locked tokens.

        This actor requires that is_me is True, and that the expiration datetime is after the existing
        locking schedule of this miner, or an exception will be raised.

        :param target_value:  The quantity of tokens in the smallest denomination.
        :param expiration: The new expiration date to set.
        :return: Returns the blockchain transaction hash

        """

        if not self.is_me:
            raise self.MinerError("Cannot execute contract staking functions with a non-self Miner instance.")
        if additional_periods and expiration:
            raise ValueError("Pass the number of lock periods or an expiration MayaDT; not both.")

        _first_period, last_period, locked_value = self.miner_agent.get_stake_info(
            miner_address=self.ether_address, stake_index=stake_index)
        if expiration:
            additional_periods = datetime_to_period(datetime=expiration) - last_period

            if additional_periods <= 0:
                raise self.MinerError("Expiration {} must be at least 1 period from now.".format(expiration))

        if target_value >= locked_value:
            raise self.MinerError("Cannot divide stake; Value must be less than the specified stake value.")

        # Ensure both halves are for valid amounts
        validate_stake_amount(amount=target_value)
        validate_stake_amount(amount=locked_value-target_value)

        tx = self.miner_agent.divide_stake(miner_address=self.ether_address,
                                           stake_index=stake_index,
                                           target_value=target_value,
                                           periods=additional_periods)

        self.blockchain.wait_for_receipt(tx)
        return tx

    def __validate_stake(self, amount: int, lock_periods: int) -> bool:
        if not self.is_me:
            raise self.MinerError("Cannot execute contract staking functions with a non-self Miner instance.")

        from .constants import validate_locktime, validate_stake_amount
        assert validate_stake_amount(amount=amount)
        assert validate_locktime(lock_periods=lock_periods)

        if not self.token_balance >= amount:
            raise self.MinerError("Insufficient miner token balance ({balance})".format(balance=self.token_balance))
        else:
            return True

    def stake(self, amount: int, lock_periods: int=None, expiration: maya.MayaDT=None, entire_balance: bool=False) -> dict:
        """
        High level staking method for Miners.

        :param amount: Amount of tokens to stake denominated in the smallest unit.
        :param lock_periods: Duration of stake in periods.
        :param expiration: A MayaDT object representing the time the stake expires; used to calculate lock_periods.
        :param entire_balance: If True, stake the entire balance of this node, or the maximum possible.

        """

        if not self.is_me:
            raise self.MinerError("Cannot execute contract staking functions with a non-self Miner instance.")
        if lock_periods and expiration:
            raise ValueError("Pass the number of lock periods or an expiration MayaDT; not both.")
        if entire_balance and amount:
            raise self.MinerError("Specify an amount or entire balance, not both")

        if expiration:
            lock_periods = calculate_period_duration(future_time=expiration)
        if entire_balance is True:
            amount = self.token_balance

        amount, lock_periods = int(amount), int(lock_periods)  # Manual type checks below this point in the stack;
        staking_transactions = OrderedDict()                   # Time series of txhases

        # Validate
        amount = self.blockchain.interface.w3.toInt(amount)
        assert self.__validate_stake(amount=amount, lock_periods=lock_periods)

        # Transact
        approve_txhash, initial_deposit_txhash = self.deposit(amount=amount, lock_periods=lock_periods)
        self._transaction_cache.append((datetime.utcnow(), initial_deposit_txhash))

        return staking_transactions

    #
    # Reward and Collection
    #
    def confirm_activity(self) -> str:
        """Miner rewarded for every confirmed period"""

        if not self.is_me:
            raise self.MinerError("Cannot execute contract staking functions with a non-self Miner instance.")

        txhash = self.miner_agent.confirm_activity(node_address=self.ether_address)
        self._transaction_cache.append((datetime.utcnow(), txhash))

        return txhash

    def mint(self) -> Tuple[str, str]:
        """Computes and transfers tokens to the miner's account"""

        if not self.is_me:
            raise self.MinerError("Cannot execute contract staking functions with a non-self Miner instance.")

        mint_txhash = self.miner_agent.mint(node_address=self.ether_address)
        self._transaction_cache.append((datetime.utcnow(), mint_txhash))

        return mint_txhash

    def collect_policy_reward(self, policy_manager):
        """Collect rewarded ETH"""

        if not self.is_me:
            raise self.MinerError("Cannot execute contract staking functions with a non-self Miner instance.")

        policy_reward_txhash = policy_manager.collect_policy_reward(collector_address=self.ether_address)
        self._transaction_cache.append((datetime.utcnow(), policy_reward_txhash))

        return policy_reward_txhash

    def collect_staking_reward(self) -> str:
        """Withdraw tokens rewarded for staking."""

        if not self.is_me:
            raise self.MinerError("Cannot execute contract staking functions with a non-self Miner instance.")

        collection_txhash = self.miner_agent.collect_staking_reward(collector_address=self.ether_address)
        self._transaction_cache.append((datetime.utcnow(), collection_txhash))

        return collection_txhash

    #
    # Miner Contract Datastore
    #

    def publish_datastore(self, data) -> str:
        """Publish new data to the MinerEscrow contract as a public record associated with this miner."""

        if not self.is_me:
            raise self.MinerError("Cannot write to contract datastore with a non-self Miner instance.")

        txhash = self.miner_agent._publish_datastore(node_address=self.ether_address, data=data)
        self._transaction_cache.append((datetime.utcnow(), txhash))
        return txhash

    def read_datastore(self, index: int=None, refresh=False):
        """
        Read a value from the nodes datastore, within the MinersEscrow ethereum contract.
        since there may be multiple values, select one, and return it. The most recently
        pushed entry is returned by default, and can be specified with the index parameter.

        If refresh it True, read the node's data from the blockchain before returning.

        """

        if refresh is True:
            self.__node_datastore = self.miner_agent._fetch_node_datastore(node_address=self.ether_address)

        if index is None:
            datastore_entries = self.miner_agent._get_datastore_entries(node_address=self.ether_address)
            index = datastore_entries - 1         # return the last, most recently result

        try:
            stored_value = next(itertools.islice(self.__node_datastore, index, index+1))
        except StopIteration:
            if self.miner_agent._get_datastore_entries(node_address=self.ether_address) == 0:
                stored_value = constants.EMPTY_NODE_DATASTORE
            else:
                raise
        return stored_value


class PolicyAuthor(NucypherTokenActor):
    """Alice base class for blockchain operations, mocking up new policies!"""

    def __init__(self, policy_agent: PolicyAgent=None, *args, **kwargs):
        """
        :param policy_agent: A policy agent with the blockchain attached; If not passed, A default policy
        agent and blockchain connection will be created from default values.

        """

        if policy_agent is None:
            # From defaults
            self.token_agent = NucypherTokenAgent()
            self.miner_agent = MinerAgent(token_agent=self.token_agent)
            self.policy_agent = PolicyAgent(miner_agent=self.miner_agent)
        else:
            # From agent
            self.policy_agent = policy_agent
            self.miner_agent = policy_agent.miner_agent
            self.token_agent = policy_agent.miner_agent.token_agent

        self.__sampled_ether_addresses = set()  # TODO: uptake into node learning api with high priority
        super().__init__(token_agent=self.policy_agent.token_agent, *args, **kwargs)

    def recruit(self, quantity: int, **options) -> None:
        """
        Uses sampling logic to gather miners from the blockchain and
        caches the resulting node ethereum addresses.

        :param quantity: Number of ursulas to sample from the blockchain.
        :return: None; Since it only mutates self

        """

        miner_addresses = self.policy_agent.miner_agent.sample(quantity=quantity, **options)
        self.__sampled_ether_addresses.update(miner_addresses)

    def create_policy(self, *args, **kwargs):
        """
        Hence the name, a PolicyAuthor can create
        a BlockchainPolicy with themself as the author.

        :return: Returns a newly authored BlockchainPolicy with n proposed arrangements.

        """

        from nucypher.blockchain.eth.policies import BlockchainPolicy
        blockchain_policy = BlockchainPolicy(author=self, *args, **kwargs)
        return blockchain_policy
