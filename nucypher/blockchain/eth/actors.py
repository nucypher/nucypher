from collections import OrderedDict
from datetime import datetime
from typing import Tuple, List, Union, Generator

from nucypher.blockchain.eth.agents import NucypherTokenAgent, MinerAgent, PolicyAgent
from constant_sorrow import constants



class NucypherTokenActor:
    """
    Concrete base class for any actor that will interface with NuCypher's ethereum smart contracts
    """

    class ActorError(Exception):
        pass

    def __init__(self, ether_address: Union[str, bytes, None]=None,
                 token_agent: NucypherTokenAgent=None, *args, **kwargs):

        # Auto-connect, if needed
        self.token_agent = token_agent if token_agent is not None else NucypherTokenAgent()

        self.__ether_address = ether_address if ether_address is not None else constants.UNKNOWN_ACTOR
        self._transaction_cache = list()  # track transactions transmitted

    def __repr__(self):
        class_name = self.__class__.__name__
        r = "{}(address='{}')"
        r = r.format(class_name, self.ether_address)
        return r

    @classmethod
    def from_config(cls, config):
        raise NotImplementedError

    #
    # Crypto-asset balances
    #
    @property
    def ether_address(self):
        return self.__ether_address

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
    Ursula, practically carrying a pickaxe.
    """

    class MinerError(NucypherTokenActor.ActorError):
        pass

    def __init__(self, miner_agent: MinerAgent=None, *args, **kwargs):
        miner_agent = miner_agent if miner_agent is not None else MinerAgent()
        super().__init__(token_agent=miner_agent.token_agent, *args, **kwargs)

        # Extrapolate dependencies
        self.miner_agent = miner_agent
        self.token_agent = miner_agent.token_agent
        self.blockchain = self.token_agent.blockchain

        # Establish initial state
        self.__locked_tokens = constants.LOCKED_TOKENS_UNAVAILIBLE
        self.__node_datastore = constants.NODE_DATA_UNAVAILIBLE

        if self.ether_address is not constants.UNKNOWN_ACTOR:
            self.__cache_locked_tokens()  # initial check-in with the blockchain
            self.__cache_node_data()

    @classmethod
    def from_config(cls, blockchain_config) -> 'Miner':

        # Use BlockchainConfig to default to the first wallet address
        wallet_address = blockchain_config.wallet_addresses[0]

        instance = cls(ether_address=wallet_address)
        return instance

    #
    # Deposits
    #
    def _approve_escrow(self, amount: int) -> str:
        """Approve the transfer of token from the miner's address to the escrow contract."""

        txhash = self.token_agent.contract.functions.approve(self.miner_agent.contract_address, amount).transact({'from': self.ether_address})
        self.blockchain.wait_for_receipt(txhash)

        self._transaction_cache.append((datetime.utcnow(), txhash))

        return txhash

    def _send_tokens_to_escrow(self, amount, lock_periods) -> str:
        """Send tokes to the escrow from the miner's address"""

        deposit_txhash = self.miner_agent.contract.functions.deposit(amount, lock_periods).transact({'from': self.ether_address})

        self.blockchain.wait_for_receipt(deposit_txhash)
        self._transaction_cache.append((datetime.utcnow(), deposit_txhash))

        return deposit_txhash

    def deposit(self, amount: int, lock_periods: int) -> Tuple[str, str]:
        """Public facing method for token locking."""
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
        lock_txhash = self.miner_agent.contract.functions.switchLock().transact({'from': self.ether_address})
        self.blockchain.wait_for_receipt(lock_txhash)

        self._transaction_cache.append((datetime.utcnow(), lock_txhash))
        return lock_txhash

    def __validate_stake(self, amount: int, lock_periods: int) -> bool:

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
        """

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

        txhash = self.miner_agent.contract.functions.confirmActivity().transact({'from': self.ether_address})
        self.blockchain.wait_for_receipt(txhash)

        self._transaction_cache.append((datetime.utcnow(), txhash))

        return txhash

    def mint(self) -> Tuple[str, str]:
        """Computes and transfers tokens to the miner's account"""

        mint_txhash = self.miner_agent.contract.functions.mint().transact({'from': self.ether_address})

        self.blockchain.wait_for_receipt(mint_txhash)
        self._transaction_cache.append((datetime.utcnow(), mint_txhash))

        return mint_txhash

    def collect_policy_reward(self, policy_manager):
        """Collect rewarded ETH"""

        policy_reward_txhash = policy_manager.contract.functions.withdraw().transact({'from': self.ether_address})
        self.blockchain.wait_for_receipt(policy_reward_txhash)

        self._transaction_cache.append((datetime.utcnow(), policy_reward_txhash))

        return policy_reward_txhash

    def collect_staking_reward(self) -> str:
        """Withdraw tokens rewarded for staking."""

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

    def publish_datastore(self, data) -> str:
        """Store new data"""

        txhash = self.miner_agent.contract.functions.setMinerId(data).transact({'from': self.ether_address})
        self.blockchain.wait_for_receipt(txhash)

        self._transaction_cache.append((datetime.utcnow(), txhash))

        return txhash

    def __fetch_data(self) -> tuple:
        """Retrieve all asosciated contract data for this miner."""

        count_bytes = self.miner_agent.contract.functions.getMinerIdsLength(self.ether_address).call()
        count = self.blockchain.interface.w3.toInt(count_bytes)

        miner_ids = list()
        for index in range(count):
            miner_id = self.miner_agent.contract.functions.getMinerId(self.ether_address, index).call()
            miner_ids.append(miner_id)
        return tuple(miner_ids)

    def __cache_node_data(self) -> None:
        """Query the MinersEscrow contract for the data stored for this miner."""
        self.__node_datastore = self.__fetch_data()

    def read_datastore(self, index: int=None, refresh=False):
        """
        Read a value from the nodes datastore, within the MinersEscrow ethereum contract.
        since there may be multiple values, select one, and return it. The most recently
        pushed entry is returned by default, and can be specified with the index parameter.

        If refresh it True, read the node's data from the blockchain before returning.
        """
        index = index if index is not None else -1  # return the last, most recently result
        if refresh is True:
            self.__cache_locked_tokens()
        try:
            stored_value = self.__node_datastore[index]
        except IndexError:
            stored_value = constants.EMPTY_NODE_DATASTORE

        return stored_value


class PolicyAuthor(NucypherTokenActor):
    """Alice, mocking up new policies!"""

    def __init__(self, policy_agent: PolicyAgent=None, *args, **kwargs):

        # From defaults
        if policy_agent is None:
            # all defaults
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