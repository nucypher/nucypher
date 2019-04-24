"""
This file is part of nucypher.

nucypher is free software: you can redistribute it and/or modify
it under the terms of the GNU Affero General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

nucypher is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU Affero General Public License for more details.

You should have received a copy of the GNU Affero General Public License
along with nucypher.  If not, see <https://www.gnu.org/licenses/>.
"""

import json
from datetime import datetime
from json import JSONDecodeError
from typing import Tuple, List, Dict, Union

import maya
from constant_sorrow.constants import (
    CONTRACT_NOT_DEPLOYED,
    NO_DEPLOYER_ADDRESS,
    EMPTY_STAKING_SLOT,
    UNKNOWN_STAKES,
    NOT_STAKING,
    NO_STAKES,
    STRANGER_MINER
)
from eth_tester.exceptions import TransactionFailed
from twisted.internet import task, reactor
from twisted.logger import Logger

from nucypher.blockchain.economics import TokenEconomics
from nucypher.blockchain.eth.agents import (
    NucypherTokenAgent,
    MinerAgent,
    PolicyAgent,
    MiningAdjudicatorAgent,
    EthereumContractAgent
)
from nucypher.blockchain.eth.chains import Blockchain
from nucypher.blockchain.eth.deployers import (
    NucypherTokenDeployer,
    MinerEscrowDeployer,
    PolicyManagerDeployer,
    UserEscrowProxyDeployer,
    UserEscrowDeployer,
    MiningAdjudicatorDeployer
)
from nucypher.blockchain.eth.interfaces import BlockchainDeployerInterface
from nucypher.blockchain.eth.registry import AllocationRegistry
from nucypher.blockchain.eth.token import NU, Stake
from nucypher.blockchain.eth.utils import datetime_to_period, calculate_period_duration


def only_me(func):
    """Decorator to enforce invocation of permissioned actor methods"""
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

    def __init__(self, checksum_address: str = None, blockchain: Blockchain = None):
        """
        :param checksum_address:  If not passed, we assume this is an unknown actor
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
    def eth_balance(self) -> int:
        """Return this actors's current ETH balance"""
        balance = self.token_agent.blockchain.interface.w3.eth.getBalance(self.checksum_public_address)
        return self.blockchain.interface.w3.fromWei(balance, 'ether')

    @property
    def token_balance(self) -> NU:
        """Return this actors's current token balance"""
        balance = int(self.token_agent.get_balance(address=self.checksum_public_address))
        nu_balance = NU(balance, 'NuNit')
        return nu_balance


class Deployer(NucypherTokenActor):

    # Registry of deployer classes
    deployers = (
        NucypherTokenDeployer,
        MinerEscrowDeployer,
        PolicyManagerDeployer,
        MiningAdjudicatorDeployer,
        UserEscrowProxyDeployer,
    )

    contract_names = tuple(a.registry_contract_name for a in EthereumContractAgent.__subclasses__())

    __interface_class = BlockchainDeployerInterface

    def __init__(self,
                 blockchain: Blockchain,
                 deployer_address: str = None,
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
            self.adjudicator_agent = MiningAdjudicatorAgent(blockchain=blockchain)

        self.user_escrow_deployers = dict()

        self.deployers = {
            NucypherTokenDeployer.contract_name: self.deploy_token_contract,
            MinerEscrowDeployer.contract_name: self.deploy_miner_contract,
            PolicyManagerDeployer.contract_name: self.deploy_policy_contract,
            UserEscrowProxyDeployer.contract_name: self.deploy_escrow_proxy,
            MiningAdjudicatorDeployer.contract_name: self.deploy_mining_adjudicator_contract,
        }

        self.log = Logger("Deployment-Actor")

    def __repr__(self):
        r = '{name}({blockchain}, {deployer_address})'.format(name=self.__class__.__name__,
                                                              blockchain=self.blockchain,
                                                              deployer_address=self.deployer_address)
        return r

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
    def token_balance(self) -> NU:
        if self.token_agent is CONTRACT_NOT_DEPLOYED:
            message = f"{self.token_agent.contract_name} contract is not deployed, or the registry has missing records."
            raise self.ActorError(message)
        return super().token_balance

    def deploy_token_contract(self) -> dict:
        token_deployer = NucypherTokenDeployer(blockchain=self.blockchain, deployer_address=self.deployer_address)
        txhashes = token_deployer.deploy()
        self.token_agent = token_deployer.make_agent()
        return txhashes

    def deploy_miner_contract(self, secret: bytes) -> dict:
        secret = self.blockchain.interface.w3.keccak(secret)
        miner_escrow_deployer = MinerEscrowDeployer(blockchain=self.blockchain,
                                                    deployer_address=self.deployer_address,
                                                    secret_hash=secret)

        txhashes = miner_escrow_deployer.deploy()
        self.miner_agent = miner_escrow_deployer.make_agent()
        return txhashes

    def deploy_policy_contract(self, secret: bytes) -> dict:
        secret = self.blockchain.interface.w3.keccak(secret)
        policy_manager_deployer = PolicyManagerDeployer(blockchain=self.blockchain,
                                                        deployer_address=self.deployer_address,
                                                        secret_hash=secret)

        txhashes = policy_manager_deployer.deploy()
        self.policy_agent = policy_manager_deployer.make_agent()
        return txhashes

    def deploy_mining_adjudicator_contract(self, secret: bytes) -> dict:
        secret = self.blockchain.interface.w3.keccak(secret)
        mining_adjudicator_deployer = MiningAdjudicatorDeployer(blockchain=self.blockchain,
                                                                deployer_address=self.deployer_address,
                                                                secret_hash=secret)

        txhashes = mining_adjudicator_deployer.deploy()
        self.adjudicator_agent = mining_adjudicator_deployer.make_agent()
        return txhashes

    def deploy_escrow_proxy(self, secret: bytes) -> dict:
        secret = self.blockchain.interface.w3.keccak(secret)
        escrow_proxy_deployer = UserEscrowProxyDeployer(blockchain=self.blockchain,
                                                        deployer_address=self.deployer_address,
                                                        secret_hash=secret)

        txhashes = escrow_proxy_deployer.deploy()
        return txhashes

    def deploy_user_escrow(self, allocation_registry: AllocationRegistry) -> UserEscrowDeployer:
        user_escrow_deployer = UserEscrowDeployer(blockchain=self.blockchain,
                                                  deployer_address=self.deployer_address,
                                                  allocation_registry=allocation_registry)

        user_escrow_deployer.deploy()
        principal_address = user_escrow_deployer.contract.address
        self.user_escrow_deployers[principal_address] = user_escrow_deployer
        return user_escrow_deployer

    def deploy_network_contracts(self,
                                 miner_secret: bytes,
                                 policy_secret: bytes,
                                 adjudicator_secret: bytes
                                 ) -> Tuple[dict, dict]:
        """
        Musketeers, if you will; Deploy the "big three" contracts to the blockchain.
        """
        token_txhashes = self.deploy_token_contract()
        miner_txhashes = self.deploy_miner_contract(secret=miner_secret)
        policy_txhashes = self.deploy_policy_contract(secret=policy_secret)
        adjudicator_txhashes = self.deploy_mining_adjudicator_contract(secret=adjudicator_secret)

        txhashes = {
            NucypherTokenDeployer.contract_name: token_txhashes,
            MinerEscrowDeployer.contract_name: miner_txhashes,
            PolicyManagerDeployer.contract_name: policy_txhashes,
            MiningAdjudicatorDeployer.contract_name: adjudicator_txhashes
        }

        agents = {
            NucypherTokenDeployer.contract_name: self.token_agent,
            MinerEscrowDeployer.contract_name: self.miner_agent,
            PolicyManagerDeployer.contract_name: self.policy_agent,
            MiningAdjudicatorDeployer.contract_name: self.adjudicator_agent
        }

        return txhashes, agents

    def deploy_beneficiary_contracts(self,
                                     allocations: List[Dict[str, Union[str, int]]],
                                     allocation_outfile: str = None,
                                     allocation_registry: AllocationRegistry = None,
                                     crash_on_failure: bool = True,
                                     ) -> Dict[str, dict]:
        """

        Example allocation dataset (one year is 31536000 seconds):

        data = [{'address': '0xdeadbeef', 'amount': 100, 'duration': 31536000},
                {'address': '0xabced120', 'amount': 133432, 'duration': 31536000*2},
                {'address': '0xf7aefec2', 'amount': 999, 'duration': 31536000*3}]
        """
        if allocation_registry and allocation_outfile:
            raise self.ActorError("Pass either allocation registry or allocation_outfile, not both.")
        if allocation_registry is None:
            allocation_registry = AllocationRegistry(registry_filepath=allocation_outfile)

        allocation_txhashes, failed = dict(), list()
        for allocation in allocations:
            deployer = self.deploy_user_escrow(allocation_registry=allocation_registry)

            try:
                txhashes = deployer.deliver(value=allocation['amount'],
                                            duration=allocation['duration'],
                                            beneficiary_address=allocation['address'])
            except TransactionFailed:
                if crash_on_failure:
                    raise
                self.log.debug(f"Failed allocation transaction for {allocation['amount']} to {allocation['address']}")
                failed.append(allocation)
                continue

            else:
                allocation_txhashes[allocation['address']] = txhashes

        if failed:
            # TODO: More with these failures: send to isolated logfile, and reattempt
            self.log.critical(f"FAILED TOKEN ALLOCATION - {len(failed)} Allocations failed.")

        return allocation_txhashes

    @staticmethod
    def __read_allocation_data(filepath: str) -> list:
        with open(filepath, 'r') as allocation_file:
            data = allocation_file.read()
            try:
                allocation_data = json.loads(data)
            except JSONDecodeError:
                raise
        return allocation_data

    def deploy_beneficiaries_from_file(self,
                                       allocation_data_filepath: str,
                                       allocation_outfile: str = None) -> dict:

        allocations = self.__read_allocation_data(filepath=allocation_data_filepath)
        txhashes = self.deploy_beneficiary_contracts(allocations=allocations, allocation_outfile=allocation_outfile)
        return txhashes


class Miner(NucypherTokenActor):
    """
    Ursula baseclass for blockchain operations, practically carrying a pickaxe.
    """

    __current_period_sample_rate = 60*60  # seconds

    class MinerError(NucypherTokenActor.ActorError):
        pass

    def __init__(self,
                 is_me: bool,
                 start_staking_loop: bool = True,
                 economics: TokenEconomics = None,
                 *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)

        self.log = Logger("miner")
        self.is_me = is_me

        if not economics:
            economics = TokenEconomics()
        self.economics = economics

        #
        # Blockchain
        #

        if is_me:
            self.token_agent = NucypherTokenAgent(blockchain=self.blockchain)

            # Staking Loop
            self.__current_period = None
            self._abort_on_staking_error = True
            self._staking_task = task.LoopingCall(self.heartbeat)

        else:
            self.token_agent = STRANGER_MINER

        self.miner_agent = MinerAgent(blockchain=self.blockchain)

        #
        # Stakes
        #

        self.__stakes = UNKNOWN_STAKES
        self.__start_time = NOT_STAKING
        self.__uptime_period = NOT_STAKING
        self.__terminal_period = UNKNOWN_STAKES

        self.__read_stakes()  # "load-in":  Read on-chain stakes

        # Start the callbacks if there are active stakes
        if (self.stakes is not NO_STAKES) and start_staking_loop:
            self.stake()

    #
    # Staking
    #

    @only_me
    def stake(self, confirm_now: bool = True) -> None:
        """
        High-level staking looping call initialization, this function aims
        to be safely called at any time - For example, it is okay to call
        this function multiple times within the same period.
        """
        # Get the last stake end period of all stakes
        terminal_period = max(stake.end_period for stake in self.stakes)

        if confirm_now:
            self.confirm_activity()

        # record start time and periods
        self.__start_time = maya.now()
        self.__uptime_period = self.miner_agent.get_current_period()
        self.__terminal_period = terminal_period
        self.__current_period = self.__uptime_period
        self.start_staking_loop()

    @property
    def last_active_period(self) -> int:
        period = self.miner_agent.get_last_active_period(address=self.checksum_public_address)
        return period

    @only_me
    def _confirm_period(self):

        onchain_period = self.miner_agent.get_current_period()  # < -- Read from contract
        self.log.info("Checking for new period. Current period is {}".format(self.__current_period))

        # Check if the period has changed on-chain
        if self.__current_period != onchain_period:

            # Let's see how much time has passed
            # TODO: Follow-up actions for downtime
            missed_periods = onchain_period - self.last_active_period
            if missed_periods:
                self.log.warn(f"MISSED CONFIRMATION - {missed_periods} missed staking confirmations detected!")
                self.__read_stakes()  # Invalidate the stake cache

            # Check for stake expiration and exit
            stake_expired = self.__current_period >= self.__terminal_period
            if stake_expired:
                self.log.info('STOPPED STAKING - Final stake ended.')
                return True

            # Write to Blockchain
            self.confirm_activity()

            # Update local period cache
            self.__current_period = onchain_period
            self.log.info("Confirmed activity for period {}".format(self.__current_period))

    def heartbeat(self):
        """Used with LoopingCall"""
        try:
            self._confirm_period()
        except Exception:
            raise

    def _crash_gracefully(self, failure=None):
        """
        A facility for crashing more gracefully in the event that an exception is unhandled in a different thread.
        """
        self._crashed = failure
        failure.raiseException()

    def handle_staking_errors(self, *args, **kwargs):
        failure = args[0]
        if self._abort_on_staking_error:
            self.log.critical("Unhandled error during node staking.  Attempting graceful crash.")
            reactor.callFromThread(self._crash_gracefully, failure=failure)
        else:
            self.log.warn("Unhandled error during node learning: {}".format(failure.getTraceback()))

    @only_me
    def start_staking_loop(self, now=True) -> None:
        if self._staking_task.running:
            return
        d = self._staking_task.start(interval=self.__current_period_sample_rate, now=now)
        d.addErrback(self.handle_staking_errors)
        self.log.info(f"STARTED STAKING - Scheduled end period is currently {self.__terminal_period}")

    @property
    def is_staking(self) -> bool:
        """Checks if this Miner currently has active stakes / locked tokens."""
        return bool(self.locked_tokens > NU.ZERO())

    def locked_tokens(self, periods: int = 0) -> NU:
        """Returns the amount of tokens this miner has locked for a given duration in periods."""
        raw_value = self.miner_agent.get_locked_tokens(miner_address=self.checksum_public_address, periods=periods)
        value = NU.from_nunits(raw_value)
        return value

    @property
    def current_stake(self) -> NU:
        """
        The total number of staked tokens, either locked or unlocked in the current period.
        """

        if self.stakes:
            return NU(sum(int(stake.value) for stake in self.stakes), 'NuNit')
        else:
            return NU.ZERO()

    @only_me
    def divide_stake(self,
                     stake_index: int,
                     target_value: NU,
                     additional_periods: int = None,
                     expiration: maya.MayaDT = None) -> tuple:

        # Calculate duration in periods
        if additional_periods and expiration:
            raise ValueError("Pass the number of lock periods or an expiration MayaDT; not both.")

        # Select stake to divide from local cache
        try:
            current_stake = self.stakes[stake_index]
        except KeyError:
            if len(self.stakes):
                message = f"Cannot divide stake - No stake exists with index {stake_index}."
            else:
                message = "Cannot divide stake - There are no active stakes."
            raise Stake.StakingError(message)

        # Calculate stake duration in periods
        if expiration:
            additional_periods = datetime_to_period(datetime=expiration) - current_stake.end_period
            if additional_periods <= 0:
                raise Stake.StakingError(f"New expiration {expiration} must be at least 1 period from the "
                                         f"current stake's end period ({current_stake.end_period}).")

        # Do it already!
        modified_stake, new_stake = current_stake.divide(target_value=target_value,
                                                         additional_periods=additional_periods)

        # Update staking cache
        self.__read_stakes()

        return modified_stake, new_stake

    @only_me
    def initialize_stake(self,
                         amount: NU,
                         lock_periods: int = None,
                         expiration: maya.MayaDT = None,
                         entire_balance: bool = False) -> Stake:

        """Create a new stake."""

        #
        # Duration
        #

        if lock_periods and expiration:
            raise ValueError("Pass the number of lock periods or an expiration MayaDT; not both.")
        if expiration:
            lock_periods = calculate_period_duration(future_time=expiration)

        #
        # Value
        #

        if entire_balance and amount:
            raise ValueError("Specify an amount or entire balance, not both")
        if entire_balance:
            amount = self.token_balance
        if not self.token_balance >= amount:
            raise self.MinerError(f"Insufficient token balance ({self.token_agent}) for new stake initialization of {amount}")

        # Ensure the new stake will not exceed the staking limit
        if (self.current_stake + amount) > self.economics.maximum_allowed_locked:
            raise Stake.StakingError(f"Cannot divide stake - Maximum stake value exceeded with a target value of {amount}.")

        #
        # Stake
        #

        # Write to blockchain
        new_stake = Stake.initialize_stake(miner=self, amount=amount, lock_periods=lock_periods)
        self.__read_stakes()  # Update local staking cache
        return new_stake

    #
    # Staking Cache
    #

    def __read_stakes(self) -> None:
        """Rewrite the local staking cache by reading on-chain stakes"""

        existing_records = len(self.__stakes)

        # Candidate replacement cache values
        onchain_stakes, terminal_period = list(), 0

        # Read from blockchain
        stakes_reader = self.miner_agent.get_all_stakes(miner_address=self.checksum_public_address)

        for onchain_index, stake_info in enumerate(stakes_reader):

            if not stake_info:
                # This stake index is empty on-chain
                onchain_stake = EMPTY_STAKING_SLOT

            else:
                # On-chain stake detected
                onchain_stake = Stake.from_stake_info(miner=self,
                                                      stake_info=stake_info,
                                                      index=onchain_index)

                # Search for the terminal period
                if onchain_stake.end_period > terminal_period:
                    terminal_period = onchain_stake.end_period

            # Store the replacement stake
            onchain_stakes.append(onchain_stake)

        # Commit the new stake and terminal values to the cache
        if not onchain_stakes:
            self.__stakes = NO_STAKES.bool_value(False)
        else:
            self.__terminal_period = terminal_period
            self.__stakes = onchain_stakes

        # Record most recent cache update
        self.__updated = maya.now()
        new_records = existing_records - len(self.__stakes)
        self.log.debug(f"Updated local staking cache ({new_records} new records).")

    def refresh_staking_cache(self) -> None:
        """Public staking cache invalidation method"""
        return self.__read_stakes()

    @property
    def stakes(self) -> List[Stake]:
        """Return all cached stake instances from the blockchain."""
        return self.__stakes

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

    def calculate_reward(self) -> int:
        staking_reward = self.miner_agent.calculate_staking_reward(checksum_address=self.checksum_public_address)
        return staking_reward

    @only_me
    def collect_policy_reward(self, collector_address=None, policy_agent: PolicyAgent = None):
        """Collect rewarded ETH"""
        policy_agent = policy_agent if policy_agent is not None else PolicyAgent(blockchain=self.blockchain)

        withdraw_address = collector_address or self.checksum_public_address
        policy_reward_txhash = policy_agent.collect_policy_reward(collector_address=withdraw_address, miner_address=self.checksum_public_address)
        self._transaction_cache.append((datetime.utcnow(), policy_reward_txhash))
        return policy_reward_txhash

    @only_me
    def collect_staking_reward(self) -> str:
        """Withdraw tokens rewarded for staking."""
        collection_txhash = self.miner_agent.collect_staking_reward(checksum_address=self.checksum_public_address)
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
        blockchain_policy = BlockchainPolicy(alice=self, *args, **kwargs)
        return blockchain_policy
