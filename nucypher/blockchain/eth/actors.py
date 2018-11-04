"""
This file is part of nucypher.

nucypher is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

nucypher is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with nucypher.  If not, see <https://www.gnu.org/licenses/>.
"""
import json
from collections import OrderedDict
from json import JSONDecodeError
from twisted.logger import Logger

import maya
from constant_sorrow import constants
from constant_sorrow.constants import CONTRACT_NOT_DEPLOYED, NO_CONTRACT_AVAILABLE, NO_DEPLOYER_ADDRESS
from datetime import datetime
from twisted.internet import task, reactor
from typing import Tuple, List, Dict, Union

from nucypher.blockchain.eth.agents import NucypherTokenAgent, MinerAgent, PolicyAgent
from nucypher.blockchain.eth.chains import Blockchain
from nucypher.blockchain.eth.deployers import NucypherTokenDeployer, MinerEscrowDeployer, PolicyManagerDeployer, \
    UserEscrowProxyDeployer, UserEscrowDeployer
from nucypher.blockchain.eth.interfaces import BlockchainDeployerInterface
from nucypher.blockchain.eth.registry import EthereumContractRegistry, AllocationRegistry
from nucypher.blockchain.eth.sol.compile import SolidityCompiler
from nucypher.blockchain.eth.utils import (datetime_to_period,
                                           validate_stake_amount,
                                           validate_locktime,
                                           calculate_period_duration)


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
                 blockchain: Blockchain = None
                 ) -> None:
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
            self.checksum_public_address = checksum_address  # type: str

        if blockchain is None:
            blockchain = Blockchain.connect()
        self.blockchain = blockchain

        self.token_agent = NucypherTokenAgent()
        self._transaction_cache = list()  # type: list # track transactions transmitted

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


class Deployer(NucypherTokenActor):

    __interface_class = BlockchainDeployerInterface

    def __init__(self,
                 blockchain: Blockchain,
                 deployer_address: str = None,
                 allocation_registry: AllocationRegistry = None,
                 bare: bool = True
                 ) -> None:

        self.blockchain = blockchain
        self.__deployer_address = NO_DEPLOYER_ADDRESS
        if deployer_address:
            self.deployer_address = deployer_address

        if not bare:
            self.token_agent = NucypherTokenAgent(blockchain=blockchain)
            self.miner_agent = MinerAgent(blockchain=blockchain)
            self.policy_agent = PolicyAgent(blockchain=blockchain)

        self.allocation_registy = allocation_registry
        self.user_escrow_deployers = dict()

    @classmethod
    def from_blockchain(cls, provider_uri: str, registry=None, *args, **kwargs):
        blockchain = Blockchain.connect(provider_uri=provider_uri, registry=registry)
        instance = cls(blockchain=blockchain, *args, **kwargs)
        return instance

    @property
    def deployer_address(self):
        return self.blockchain.interface.deployer_address

    @deployer_address.setter
    def deployer_address(self, value):
        """Used for validated post-init setting of deployer's address"""
        self.blockchain.interface.deployer_address = value

    @property
    def token_balance(self):
        if self.token_agent is CONTRACT_NOT_DEPLOYED:
            raise self.ActorError("Token contract not deployed")
        return super().token_balance

    def deploy_token_contract(self):

        token_deployer = NucypherTokenDeployer(blockchain=self.blockchain, deployer_address=self.deployer_address)

        token_deployer.deploy()
        self.token_agent = token_deployer.make_agent()

    def deploy_miner_contract(self, secret):

        miner_escrow_deployer = MinerEscrowDeployer(deployer_address=self.deployer_address,
                                                    secret_hash=secret)

        miner_escrow_deployer.deploy()
        self.miner_agent = miner_escrow_deployer.make_agent()

    def deploy_policy_contract(self, secret):

        policy_manager_deployer = PolicyManagerDeployer(deployer_address=self.deployer_address,
                                                        secret_hash=secret)

        policy_manager_deployer.deploy()
        self.policy_agent = policy_manager_deployer.make_agent()

    def deploy_escrow_proxy(self, secret):

        escrow_proxy_deployer = UserEscrowProxyDeployer(deployer_address=self.deployer_address,
                                                        secret_hash=secret)

        escrow_proxy_deployer.deploy()
        return escrow_proxy_deployer

    def deploy_user_escrow(self):
        user_escrow_deployer = UserEscrowDeployer(deployer_address=self.deployer_address,
                                                  allocation_registry=self.allocation_registy)

        user_escrow_deployer.deploy()
        principal_address = user_escrow_deployer.contract.address
        self.user_escrow_deployers[principal_address] = user_escrow_deployer
        return user_escrow_deployer

    def deploy_network_contracts(self, miner_secret, policy_secret):
        """
        Musketeers, if you will; Deploy the "big three" contracts to the blockchain.
        """
        self.deploy_token_contract()
        self.deploy_miner_contract(secret=miner_secret)
        self.deploy_policy_contract(secret=policy_secret)

    def deploy_beneficiary_contracts(self, allocations: List[Dict[str, Union[str, int]]]) -> None:
        """

        Example allocation dataset (one year is 31540000 seconds):

        data = [{'address': '0xdeadbeef', 'amount': 100, 'duration': 31540000},
                {'address': '0xabced120', 'amount': 133432, 'duration': 31540000*2},
                {'address': '0xf7aefec2', 'amount': 999, 'duration': 31540000*3}]
        """
        for allocation in allocations:
            deployer = self.deploy_user_escrow()
            deployer.deliver(value=allocation['amount'],
                             duration=allocation['duration'],
                             beneficiary_address=allocation['address'])

    @staticmethod
    def __read_allocation_data(filepath: str):
        with open(filepath, 'r') as allocation_file:
            data = allocation_file.read()
            try:
                allocation_data = json.loads(data)
            except JSONDecodeError:
                raise
        return allocation_data

    def deploy_beneficiaries_from_file(self, allocation_data_filepath: str):
        allocations = self.__read_allocation_data(filepath=allocation_data_filepath)
        self.deploy_beneficiary_contracts(allocations=allocations)


class Miner(NucypherTokenActor):
    """
    Ursula baseclass for blockchain operations, practically carrying a pickaxe.
    """

    __current_period_sample_rate = 10

    class MinerError(NucypherTokenActor.ActorError):
        pass

    def __init__(self, is_me: bool, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.log = Logger("miner")
        self.is_me = is_me

        if is_me:
            self.token_agent = NucypherTokenAgent(blockchain=self.blockchain)

            # Staking Loop
            self.__current_period = None
            self._abort_on_staking_error = True
            self._staking_task = task.LoopingCall(self._confirm_period)

        else:
            self.token_agent = constants.STRANGER_MINER

        # Everyone!
        self.miner_agent = MinerAgent(blockchain=self.blockchain)

    #
    # Staking
    #
    @only_me
    def stake(self,
              confirm_now=False,
              resume: bool = False,
              expiration: maya.MayaDT = None,
              lock_periods: int = None,
              *args, **kwargs) -> None:

        """High-level staking daemon loop"""

        if lock_periods and expiration:
            raise ValueError("Pass the number of lock periods or an expiration MayaDT; not both.")
        if expiration:
            lock_periods = datetime_to_period(expiration)

        if resume is False:
            _staking_receipts = self.initialize_stake(expiration=expiration,
                                                      lock_periods=lock_periods,
                                                      *args, **kwargs)

        # TODO: Check if this period has already been confirmed
        # TODO: Check if there is an active stake in the current period: Resume staking daemon
        # TODO: Validation and Sanity checks

        if confirm_now:
            self.confirm_activity()

        # record start time and periods
        self.__start_time = maya.now()
        self.__uptime_period = self.miner_agent.get_current_period()
        self.__terminal_period = self.__uptime_period + lock_periods
        self.__current_period = self.__uptime_period
        self.start_staking_loop()

        #
        # Daemon
        #

    @only_me
    def _confirm_period(self):

        period = self.miner_agent.get_current_period()
        self.log.info("Checking for new period. Current period is {}".format(self.__current_period))  # TODO:  set to debug?

        if self.__current_period != period:

            # check for stake expiration
            stake_expired = self.__current_period >= self.__terminal_period
            if stake_expired:
                self.log.info('Stake duration expired')
                return True

            self.confirm_activity()
            self.__current_period = period
            self.log.info("Confirmed activity for period {}".format(self.__current_period))

    @only_me
    def _crash_gracefully(self, failure=None):
        """
        A facility for crashing more gracefully in the event that an exception
        is unhandled in a different thread, especially inside a loop like the learning loop.
        """
        self._crashed = failure
        failure.raiseException()

    @only_me
    def handle_staking_errors(self, *args, **kwargs):
        failure = args[0]
        if self._abort_on_staking_error:
            self.log.critical("Unhandled error during node staking.  Attempting graceful crash.")
            reactor.callFromThread(self._crash_gracefully, failure=failure)
        else:
            self.log.warn("Unhandled error during node learning: {}".format(failure.getTraceback()))

    @only_me
    def start_staking_loop(self, now=True):
        if self._staking_task.running:
            return False
        else:
            d = self._staking_task.start(interval=self.__current_period_sample_rate, now=now)
            d.addErrback(self.handle_staking_errors)
            self.log.info("Started staking loop")
            return d

    @property
    def is_staking(self):
        """Checks if this Miner currently has locked tokens."""
        return bool(self.locked_tokens > 0)

    @property
    def locked_tokens(self):
        """Returns the amount of tokens this miner has locked."""
        return self.miner_agent.get_locked_tokens(miner_address=self.checksum_public_address)

    @property
    def stakes(self) -> Tuple[list]:
        """Read all live stake data from the blockchain and return it as a tuple"""
        stakes_reader = self.miner_agent.get_all_stakes(miner_address=self.checksum_public_address)
        return tuple(stakes_reader)

    @only_me
    def deposit(self, amount: int, lock_periods: int) -> Tuple[str, str]:
        """Public facing method for token locking."""

        approve_txhash = self.token_agent.approve_transfer(amount=amount,
                                                           target_address=self.miner_agent.contract_address,
                                                           sender_address=self.checksum_public_address)

        deposit_txhash = self.miner_agent.deposit_tokens(amount=amount,
                                                         lock_periods=lock_periods,
                                                         sender_address=self.checksum_public_address)

        return approve_txhash, deposit_txhash

    @only_me
    def divide_stake(self,
                     stake_index: int,
                     target_value: int,
                     additional_periods: int = None,
                     expiration: maya.MayaDT = None) -> dict:
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

        assert validate_stake_amount(amount=amount)  # TODO: remove assertions..?
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

        self.log.info("{} Initialized new stake: {} tokens for {} periods".format(self.checksum_public_address, amount, lock_periods))
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
    def collect_staking_reward(self, collector_address: str) -> str:
        """Withdraw tokens rewarded for staking."""

        collection_txhash = self.miner_agent.collect_staking_reward(collector_address=collector_address)
        self._transaction_cache.append((datetime.utcnow(), collection_txhash))

        return collection_txhash


class PolicyAuthor(NucypherTokenActor):
    """Alice base class for blockchain operations, mocking up new policies!"""

    def __init__(self, checksum_address: str, *args, **kwargs) -> None:
        """
        :param policy_agent: A policy agent with the blockchain attached; If not passed, A default policy
        agent and blockchain connection will be created from default values.

        """
        super().__init__(checksum_address=checksum_address, *args, **kwargs)

        # From defaults
        self.token_agent = NucypherTokenAgent(blockchain=self.blockchain)
        self.miner_agent = MinerAgent(blockchain=self.blockchain)
        self.policy_agent = PolicyAgent(blockchain=self.blockchain)

    def recruit(self, quantity: int, **options) -> List[str]:
        """
        Uses sampling logic to gather miners from the blockchain and
        caches the resulting node ethereum addresses.

        :param quantity: Number of ursulas to sample from the blockchain.

        """

        miner_addresses = self.miner_agent.sample(quantity=quantity, **options)
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
