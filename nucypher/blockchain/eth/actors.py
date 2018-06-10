import itertools
from collections import OrderedDict
from datetime import datetime
from typing import Tuple, List, Union, Generator

from nucypher.blockchain.eth.agents import NucypherTokenAgent, MinerAgent, PolicyAgent
from constant_sorrow import constants


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

    def eth_balance(self):
        """Return this actors's current ETH balance"""
        balance = self.token_agent.blockchain.interface.w3.eth.getBalance(self.ether_address)
        return balance

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
        self.__locked_tokens = constants.LOCKED_TOKENS_UNAVAILIBLE
        self.__datastore_entries = constants.CONTRACT_DATASTORE_UNAVAILIBLE
        self.__node_datastore = constants.CONTRACT_DATASTORE_UNAVAILIBLE

        if self.ether_address is not constants.UNKNOWN_ACTOR:
            self.__cache_locked_tokens()  # initial check-in with the blockchain
            self.__fetch_node_datastore()

    @classmethod
    def from_config(cls, blockchain_config) -> 'Miner':
        """Read miner data from a configuration file, and create an miner instance."""

        # Use BlockchainConfig to default to the first wallet address
        wallet_address = blockchain_config.wallet_addresses[0]

        instance = cls(ether_address=wallet_address)
        return instance

    #
    # Deposits
    #
    def _approve_escrow(self, amount: int) -> str:
        """Approve the transfer of token from the miner's address to the escrow contract."""
        if not self.is_me:
            raise self.MinerError("Cannot execute contract staking functions with a non-self Miner instance.")

        txhash = self.token_agent.contract.functions.approve(self.miner_agent.contract_address, amount).transact({'from': self.ether_address})
        self.blockchain.wait_for_receipt(txhash)

        self._transaction_cache.append((datetime.utcnow(), txhash))

        return txhash

    def _send_tokens_to_escrow(self, amount, lock_periods) -> str:
        """Send tokes to the escrow from the miner's address"""
        if not self.is_me:
            raise self.MinerError("Cannot execute contract staking functions with a non-self Miner instance.")

        deposit_txhash = self.miner_agent.contract.functions.deposit(amount, lock_periods).transact({'from': self.ether_address})

        self.blockchain.wait_for_receipt(deposit_txhash)
        self._transaction_cache.append((datetime.utcnow(), deposit_txhash))

        return deposit_txhash

    def deposit(self, amount: int, lock_periods: int) -> Tuple[str, str]:
        """Public facing method for token locking."""
        if not self.is_me:
            raise self.MinerError("Cannot execute contract staking functions with a non-self Miner instance.")

        approve_txhash = self._approve_escrow(amount=amount)
        deposit_txhash = self._send_tokens_to_escrow(amount=amount, lock_periods=lock_periods)

        return approve_txhash, deposit_txhash

    #
    # Locking Status
    #
    def __cache_locked_tokens(self) -> None:
        """Query the contract for the amount of locked tokens on this miner's eth address and cache it"""

        self.__locked_tokens = self.miner_agent.contract.functions.getLockedTokens(self.ether_address).call()

    @property
    def is_staking(self):
        """Checks if this Miner currently has locked tokens."""

        self.__cache_locked_tokens()
        return bool(self.__locked_tokens > 0)

    @property
    def locked_tokens(self, ):
        """Returns the amount of tokens this miner has locked."""

        self.__cache_locked_tokens()
        return self.__locked_tokens

    #
    # Locking and Staking
    #
    # TODO add divide_stake method
    def switch_lock(self):
        if not self.is_me:
            raise self.MinerError("Cannot execute contract staking functions with a non-self Miner instance.")

        lock_txhash = self.miner_agent.contract.functions.switchLock().transact({'from': self.ether_address})
        self.blockchain.wait_for_receipt(lock_txhash)

        self._transaction_cache.append((datetime.utcnow(), lock_txhash))
        return lock_txhash

    def __validate_stake(self, amount: int, lock_periods: int) -> bool:
        if not self.is_me:
            raise self.MinerError("Cannot execute contract staking functions with a non-self Miner instance.")

        from .constants import validate_locktime, validate_stake_amount
        assert validate_stake_amount(amount=amount)
        assert validate_locktime(lock_periods=lock_periods)

        if not self.token_balance() >= amount:
            raise self.MinerError("Insufficient miner token balance ({balance})".format(balance=self.token_balance()))
        else:
            return True

    def stake(self, amount, lock_periods, entire_balance=False):
        """
        High level staking method for Miners.

        :param amount: Amount of tokens to stake denominated in the smallest unit.
        :param lock_periods: Duration of stake in periods.
        :param entire_balance: If True, stake the entire balance of this node, or the maximum possible.

        """
        if not self.is_me:
            raise self.MinerError("Cannot execute contract staking functions with a non-self Miner instance.")

            # manual type checking below this point; force an int to allow use of constants
        amount, lock_periods = int(amount), int(lock_periods)

        staking_transactions = OrderedDict()  # Time series of txhases

        if entire_balance and amount:
            raise self.MinerError("Specify an amount or entire balance, not both")

        if entire_balance is True:
            amount = self.miner_agent.contract.functions.getMinerInfo(self.miner_agent.MinerInfo.VALUE.value,
                                                                      self.ether_address, 0).call()
        amount = self.blockchain.interface.w3.toInt(amount)

        assert self.__validate_stake(amount=amount, lock_periods=lock_periods)

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

        txhash = self.miner_agent.contract.functions.confirmActivity().transact({'from': self.ether_address})
        self.blockchain.wait_for_receipt(txhash)

        self._transaction_cache.append((datetime.utcnow(), txhash))

        return txhash

    def mint(self) -> Tuple[str, str]:
        """Computes and transfers tokens to the miner's account"""

        if not self.is_me:
            raise self.MinerError("Cannot execute contract staking functions with a non-self Miner instance.")

        mint_txhash = self.miner_agent.contract.functions.mint().transact({'from': self.ether_address})

        self.blockchain.wait_for_receipt(mint_txhash)
        self._transaction_cache.append((datetime.utcnow(), mint_txhash))

        return mint_txhash

    def collect_policy_reward(self, policy_manager):
        """Collect rewarded ETH"""

        if not self.is_me:
            raise self.MinerError("Cannot execute contract staking functions with a non-self Miner instance.")

        policy_reward_txhash = policy_manager.contract.functions.withdraw().transact({'from': self.ether_address})
        self.blockchain.wait_for_receipt(policy_reward_txhash)

        self._transaction_cache.append((datetime.utcnow(), policy_reward_txhash))

        return policy_reward_txhash

    def collect_staking_reward(self) -> str:
        """Withdraw tokens rewarded for staking."""

        if not self.is_me:
            raise self.MinerError("Cannot execute contract staking functions with a non-self Miner instance.")

        token_amount = self.miner_agent.contract.functions.minerInfo(self.ether_address).call()[0]
        staked_amount = max(self.miner_agent.contract.functions.getLockedTokens(self.ether_address).call(),
                            self.miner_agent.contract.functions.getLockedTokens(self.ether_address, 1).call())

        collection_txhash = self.miner_agent.contract.functions.withdraw(token_amount - staked_amount).transact({'from': self.ether_address})

        self.blockchain.wait_for_receipt(collection_txhash)
        self._transaction_cache.append((datetime.utcnow(), collection_txhash))

        return collection_txhash

    #
    # Miner Datastore
    #

    def _publish_datastore(self, data) -> str:
        """Publish new data to the MinerEscrow contract as a public record associated with this miner."""

        if not self.is_me:
            raise self.MinerError("Cannot write to contract datastore with a non-self Miner instance.")

        txhash = self.miner_agent.contract.functions.setMinerId(data).transact({'from': self.ether_address})
        self.blockchain.wait_for_receipt(txhash)

        self._transaction_cache.append((datetime.utcnow(), txhash))

        return txhash

    def __fetch_node_datastore(self) -> None:
        """Cache a generator of all asosciated contract data for this miner."""

        count_bytes = self.miner_agent.contract.functions.getMinerIdsLength(self.ether_address).call()
        self.__datastore_entries = self.blockchain.interface.w3.toInt(count_bytes)

        def node_datastore_reader():
            for index in range(self.__datastore_entries):
                value = self.miner_agent.contract.functions.getMinerId(self.ether_address, index).call()
                yield value
        self.__node_datastore = node_datastore_reader()

    def _read_datastore(self, index: int=None, refresh=False):
        """
        Read a value from the nodes datastore, within the MinersEscrow ethereum contract.
        since there may be multiple values, select one, and return it. The most recently
        pushed entry is returned by default, and can be specified with the index parameter.

        If refresh it True, read the node's data from the blockchain before returning.

        """
        if refresh is True:
            self.__fetch_node_datastore()

        # return the last, most recently result
        index = index if index is not None else self.__datastore_entries - 1

        try:
            stored_value = next(itertools.islice(self.__node_datastore, index, index+1))
        except ValueError:
            if self.__datastore_entries == 0:
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

        NucypherTokenActor.__init__(self, token_agent=self.policy_agent.token_agent, *args, **kwargs)
        self._arrangements = OrderedDict()    # Track authored policies by id

    def revoke_arrangement(self, arrangement_id) -> str:
        """Get the arrangement from the cache and revoke it on the blockchain"""
        try:
            arrangement = self._arrangements[arrangement_id]
        except KeyError:
            raise self.ActorError('Not tracking arrangement {}'.format(arrangement_id))
        else:
            txhash = arrangement.revoke()
        return txhash

    def recruit(self, quantity: int, **options) -> Generator[Miner, None, None]:
        """Uses sampling logic to gather miners from the blockchain"""
        miner_addresses = self.policy_agent.miner_agent.sample(quantity=quantity, **options)
        for address in miner_addresses:
            miner = Miner(ether_address=address, miner_agent=self.miner_agent)
            yield miner

    def create_policy(self, *args, **kwargs):
        from nucypher.blockchain.eth.policies import BlockchainPolicy

        blockchain_policy = BlockchainPolicy(author=self, *args, **kwargs)
        return blockchain_policy
