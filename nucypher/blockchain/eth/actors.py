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
import os
from datetime import datetime
from decimal import Decimal
from json import JSONDecodeError
from typing import Tuple, List, Dict, Union

import click
import maya
from constant_sorrow.constants import (
    CONTRACT_NOT_DEPLOYED,
    NO_DEPLOYER_ADDRESS,
    WORKER_NOT_RUNNING,
    NO_WORKER_ASSIGNED
)
from eth_tester.exceptions import TransactionFailed
from eth_utils import is_checksum_address
from eth_utils import keccak
from twisted.logger import Logger

from nucypher.blockchain.economics import TokenEconomics
from nucypher.blockchain.eth.agents import (
    NucypherTokenAgent,
    StakingEscrowAgent,
    PolicyManagerAgent,
    AdjudicatorAgent
)
from nucypher.blockchain.eth.decorators import validate_checksum_address
from nucypher.blockchain.eth.deployers import (
    NucypherTokenDeployer,
    StakingEscrowDeployer,
    PolicyManagerDeployer,
    UserEscrowProxyDeployer,
    UserEscrowDeployer,
    AdjudicatorDeployer,
    ContractDeployer)
from nucypher.blockchain.eth.interfaces import BlockchainDeployerInterface
from nucypher.blockchain.eth.interfaces import BlockchainInterface
from nucypher.blockchain.eth.registry import AllocationRegistry
from nucypher.blockchain.eth.token import NU, Stake, StakeTracker
from nucypher.blockchain.eth.utils import datetime_to_period, calculate_period_duration
from nucypher.characters.control.emitters import StdoutEmitter
from nucypher.cli.painting import paint_contract_deployment
from nucypher.config.base import BaseConfiguration
from nucypher.config.constants import DEFAULT_CONFIG_ROOT
from nucypher.crypto.powers import TransactingPower


def only_me(func):
    """Decorator to enforce invocation of permissioned actor methods"""
    def wrapped(actor=None, *args, **kwargs):
        if not actor.is_me:
            raise actor.StakerError("You are not {}".format(actor.__class.__.__name__))
        return func(actor, *args, **kwargs)
    return wrapped


def save_receipt(actor_method):
    """Decorator to save the receipts of transmitted transactions from actor methods"""
    def wrapped(self, *args, **kwargs):
        receipt = actor_method(self, *args, **kwargs)
        self._saved_receipts.append((datetime.utcnow(), receipt))
        return receipt
    return wrapped


class NucypherTokenActor:
    """
    Concrete base class for any actor that will interface with NuCypher's ethereum smart contracts.
    """

    class ActorError(Exception):
        pass

    def __init__(self, blockchain: BlockchainInterface, checksum_address: str = None):
        """
        :param checksum_address:  If not passed, we assume this is an unknown actor
        """
        try:
            parent_address = self.checksum_address  # type: str
            if checksum_address is not None:
                if parent_address != checksum_address:
                    raise ValueError("Can't have two different addresses.")
        except AttributeError:
            self.checksum_address = checksum_address  # type: str

        self.blockchain = blockchain
        self.token_agent = NucypherTokenAgent(blockchain=self.blockchain)
        self._saved_receipts = list()  # type: list # track receipts of transmitted transactions

    def __repr__(self):
        class_name = self.__class__.__name__
        r = "{}(address='{}')"
        r = r.format(class_name, self.checksum_address)
        return r

    def __eq__(self, other) -> bool:
        """Actors are equal if they have the same address."""
        return bool(self.checksum_address == other.checksum_address)

    @property
    def eth_balance(self) -> Decimal:
        """Return this actors's current ETH balance"""
        balance = self.blockchain.client.get_balance(self.checksum_address)
        return self.blockchain.client.w3.fromWei(balance, 'ether')

    @property
    def token_balance(self) -> NU:
        """Return this actors's current token balance"""
        balance = int(self.token_agent.get_balance(address=self.checksum_address))
        nu_balance = NU(balance, 'NuNit')
        return nu_balance


class DeployerActor(NucypherTokenActor):

    __interface_class = BlockchainDeployerInterface

    #
    # Deployer classes sorted by deployment dependency order.
    #

    standard_deployer_classes = (
        NucypherTokenDeployer,
    )

    upgradeable_deployer_classes = (
        StakingEscrowDeployer,
        PolicyManagerDeployer,
        UserEscrowProxyDeployer,
        AdjudicatorDeployer,
    )

    deployer_classes = (*standard_deployer_classes, *upgradeable_deployer_classes)

    class UnknownContract(ValueError):
        pass

    def __init__(self,
                 blockchain: BlockchainDeployerInterface,
                 deployer_address: str = None,
                 client_password: str = None,
                 bare: bool = True
                 ) -> None:

        self.log = Logger("Deployment-Actor")

        self.blockchain = blockchain
        self.__deployer_address = NO_DEPLOYER_ADDRESS
        self.deployer_address = deployer_address
        self.checksum_address = self.deployer_address

        if not bare:
            self.token_agent = NucypherTokenAgent(blockchain=blockchain)
            self.staking_agent = StakingEscrowAgent(blockchain=blockchain)
            self.policy_agent = PolicyManagerAgent(blockchain=blockchain)
            self.adjudicator_agent = AdjudicatorAgent(blockchain=blockchain)

        self.user_escrow_deployers = dict()
        self.deployers = {d.contract_name: d for d in self.deployer_classes}

        self.transacting_power = TransactingPower(blockchain=blockchain,
                                                  password=client_password,
                                                  account=deployer_address)
        self.transacting_power.activate()

    def __repr__(self):
        r = '{name}({blockchain}, {deployer_address})'.format(name=self.__class__.__name__,
                                                              blockchain=self.blockchain,
                                                              deployer_address=self.deployer_address)
        return r

    @property
    def deployer_address(self):
        return self.blockchain.deployer_address

    @deployer_address.setter
    def deployer_address(self, value):
        """Used for validated post-init setting of deployer's address"""
        self.blockchain.deployer_address = value

    @property
    def token_balance(self) -> NU:
        if self.token_agent is CONTRACT_NOT_DEPLOYED:
            message = f"{self.token_agent.contract_name} contract is not deployed, or the registry has missing records."
            raise self.ActorError(message)
        return super().token_balance

    def __get_deployer(self, contract_name: str):
        try:
            Deployer = self.deployers[contract_name]
        except KeyError:
            raise self.UnknownContract(contract_name)
        return Deployer

    @staticmethod
    def collect_deployment_secret(deployer) -> str:
        secret = click.prompt(f'Enter {deployer.contract_name} Deployment Secret',
                              hide_input=True,
                              confirmation_prompt=True)
        return secret

    def collect_deployment_secrets(self) -> dict:
        secrets = dict()
        for deployer in self.upgradeable_deployer_classes:
            secrets[deployer.contract_name] = self.collect_deployment_secret(deployer)
        return secrets

    def deploy_contract(self,
                        contract_name: str,
                        gas_limit: int = None,
                        plaintext_secret: str = None,
                        progress=None
                        ) -> Tuple[dict, ContractDeployer]:

        Deployer = self.__get_deployer(contract_name=contract_name)
        deployer = Deployer(blockchain=self.blockchain, deployer_address=self.deployer_address)
        if Deployer._upgradeable:
            if not plaintext_secret:
                raise ValueError("Upgrade plaintext_secret must be passed to deploy an upgradeable contract.")
            secret_hash = keccak(bytes(plaintext_secret, encoding='utf-8'))
            txhashes = deployer.deploy(secret_hash=secret_hash, gas_limit=gas_limit, progress=progress)
        else:
            txhashes = deployer.deploy(gas_limit=gas_limit, progress=progress)
        return txhashes, deployer

    def upgrade_contract(self, contract_name: str, existing_plaintext_secret: str, new_plaintext_secret: str) -> dict:
        Deployer = self.__get_deployer(contract_name=contract_name)
        deployer = Deployer(blockchain=self.blockchain, deployer_address=self.deployer_address)
        new_secret_hash = keccak(bytes(new_plaintext_secret, encoding='utf-8'))
        txhashes = deployer.upgrade(existing_secret_plaintext=bytes(existing_plaintext_secret, encoding='utf-8'),
                                    new_secret_hash=new_secret_hash)
        return txhashes

    def rollback_contract(self, contract_name: str, existing_plaintext_secret: str, new_plaintext_secret: str):
        Deployer = self.__get_deployer(contract_name=contract_name)
        deployer = Deployer(blockchain=self.blockchain, deployer_address=self.deployer_address)
        new_secret_hash = keccak(bytes(new_plaintext_secret, encoding='utf-8'))
        txhash = deployer.rollback(existing_secret_plaintext=bytes(existing_plaintext_secret, encoding='utf-8'),
                                   new_secret_hash=new_secret_hash)
        return txhash

    def deploy_user_escrow(self, allocation_registry: AllocationRegistry):
        user_escrow_deployer = UserEscrowDeployer(blockchain=self.blockchain,
                                                  deployer_address=self.deployer_address,
                                                  allocation_registry=allocation_registry)
        user_escrow_deployer.deploy()
        principal_address = user_escrow_deployer.contract.address
        self.user_escrow_deployers[principal_address] = user_escrow_deployer
        return user_escrow_deployer

    def deploy_network_contracts(self,
                                 secrets: dict,
                                 interactive: bool = True,
                                 emitter: StdoutEmitter = None) -> dict:
        """

        :param secrets: Contract upgrade secrets dictionary
        :param interactive: If True, wait for keypress after each contract deployment
        :param emitter: A console output emitter instance. If emitter is None, no output will be echoed to the console.
        :return: Returns a dictionary of deployment receipts keyed by contract name
        """

        if interactive and not emitter:
            raise ValueError("'emitter' is a required keyword argument when interactive is True.")

        deployment_receipts = dict()
        gas_limit = None  # TODO: Gas management

        # deploy contracts
        total_deployment_transactions = 0
        for deployer_class in self.deployer_classes:
            total_deployment_transactions += deployer_class.number_of_deployment_transactions

        first_iteration = True
        with click.progressbar(length=total_deployment_transactions, label="Deployment progress") as bar:
            bar.short_limit = 0
            for deployer_class in self.deployer_classes:
                if interactive and not first_iteration:
                    click.pause(info="\nPress any key to continue")

                if emitter:
                    emitter.echo(f"\nDeploying {deployer_class.contract_name} ...")
                    bar._last_line = None
                    bar.render_progress()

                if deployer_class in self.standard_deployer_classes:
                    receipts, deployer = self.deploy_contract(contract_name=deployer_class.contract_name,
                                                              gas_limit=gas_limit,
                                                              progress=bar)
                else:
                    receipts, deployer = self.deploy_contract(contract_name=deployer_class.contract_name,
                                                              plaintext_secret=secrets[deployer_class.contract_name],
                                                              gas_limit=gas_limit,
                                                              progress=bar)

                if emitter:
                    paint_contract_deployment(contract_name=deployer_class.contract_name,
                                              receipts=receipts,
                                              contract_address=deployer.contract_address,
                                              emitter=emitter)

                deployment_receipts[deployer_class.contract_name] = receipts
                first_iteration = False

        return deployment_receipts

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

    def save_deployment_receipts(self, receipts: dict) -> str:
        filename = f'deployment-receipts-{self.deployer_address[:6]}-{maya.now().epoch}.json'
        filepath = os.path.join(DEFAULT_CONFIG_ROOT, filename)
        # TODO: Do not assume default config root
        os.makedirs(DEFAULT_CONFIG_ROOT, exist_ok=True)
        with open(filepath, 'w') as file:
            data = dict()
            for contract_name, receipts in receipts.items():
                contract_records = dict()
                for tx_name, receipt in receipts.items():
                    # Formatting
                    receipt = {item: str(result) for item, result in receipt.items()}
                    contract_records.update({tx_name: receipt for tx_name in receipts})
                data[contract_name] = contract_records
            data = json.dumps(data, indent=4)
            file.write(data)
        return filepath


class Staker(NucypherTokenActor):
    """
    Baseclass for staking-related operations on the blockchain.
    """

    class StakerError(NucypherTokenActor.ActorError):
        pass

    class InsufficientTokens(StakerError):
        pass

    def __init__(self,
                 is_me: bool,
                 economics: TokenEconomics = None,
                 *args, **kwargs) -> None:

        super().__init__(*args, **kwargs)
        self.log = Logger("staker")
        self.stake_tracker = StakeTracker(checksum_addresses=[self.checksum_address])
        self.staking_agent = StakingEscrowAgent(blockchain=self.blockchain)
        self.economics = economics or TokenEconomics()
        self.is_me = is_me
        self.__worker_address = None

    def to_dict(self) -> dict:
        stake_info = [stake.to_stake_info() for stake in self.stakes]
        worker_address = self.worker_address or BlockchainInterface.NULL_ADDRESS
        staker_funds = {'ETH': int(self.eth_balance), 'NU': int(self.token_balance)}
        staker_payload = {'staker': self.checksum_address,
                          'balances': staker_funds,
                          'worker': worker_address,
                          'stakes': stake_info}
        return staker_payload

    @classmethod
    def from_dict(cls, staker_payload: dict) -> 'Staker':
        staker = Staker(is_me=True, checksum_address=staker_payload['checksum_address'])
        return staker

    @property
    def stakes(self) -> List[Stake]:
        stakes = self.stake_tracker.stakes(checksum_address=self.checksum_address)
        return stakes

    @property
    def is_staking(self) -> bool:
        """Checks if this Staker currently has active stakes / locked tokens."""
        return bool(self.stakes)

    def locked_tokens(self, periods: int = 0) -> NU:
        """Returns the amount of tokens this staker has locked for a given duration in periods."""
        raw_value = self.staking_agent.get_locked_tokens(staker_address=self.checksum_address, periods=periods)
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

        # Update staking cache element
        self.stake_tracker.refresh(checksum_addresses=[self.checksum_address])

        return modified_stake, new_stake

    @only_me
    def initialize_stake(self,
                         amount: NU,
                         lock_periods: int = None,
                         expiration: maya.MayaDT = None,
                         entire_balance: bool = False) -> Stake:

        """Create a new stake."""

        # Duration
        if lock_periods and expiration:
            raise ValueError("Pass the number of lock periods or an expiration MayaDT; not both.")
        if expiration:
            lock_periods = calculate_period_duration(future_time=expiration)

        # Value
        if entire_balance and amount:
            raise ValueError("Specify an amount or entire balance, not both")
        if entire_balance:
            amount = self.token_balance
        if not self.token_balance >= amount:
            raise self.InsufficientTokens(f"Insufficient token balance ({self.token_agent}) "
                                          f"for new stake initialization of {amount}")

        # Ensure the new stake will not exceed the staking limit
        if (self.current_stake + amount) > self.economics.maximum_allowed_locked:
            raise Stake.StakingError(f"Cannot divide stake - "
                                     f"Maximum stake value exceeded with a target value of {amount}.")

        # Write to blockchain
        new_stake = Stake.initialize_stake(staker=self, amount=amount, lock_periods=lock_periods)

        # Update stake tracker cache element
        self.stake_tracker.refresh(checksum_addresses=[self.checksum_address])
        return new_stake

    #
    # Reward and Collection
    #

    @only_me
    @save_receipt
    def set_worker(self, worker_address: str) -> str:
        # TODO: Set a Worker for this staker, not just in StakingEscrow
        receipt = self.staking_agent.set_worker(staker_address=self.checksum_address, worker_address=worker_address)
        self.__worker_address = worker_address
        return receipt

    @property
    def worker_address(self) -> str:
        if self.__worker_address:
            return self.__worker_address
        else:
            worker_address = self.staking_agent.get_worker_from_staker(staker_address=self.checksum_address)
            self.__worker_address = worker_address

        if self.__worker_address == BlockchainInterface.NULL_ADDRESS:
            return NO_WORKER_ASSIGNED.bool_value(False)
        return self.__worker_address

    @only_me
    @save_receipt
    def mint(self) -> Tuple[str, str]:
        """Computes and transfers tokens to the staker's account"""
        receipt = self.staking_agent.mint(staker_address=self.checksum_address)
        return receipt

    def calculate_reward(self) -> int:
        staking_reward = self.staking_agent.calculate_staking_reward(staker_address=self.checksum_address)
        return staking_reward

    @only_me
    @save_receipt
    def collect_policy_reward(self, collector_address=None, policy_agent: PolicyManagerAgent = None):
        """Collect rewarded ETH"""
        policy_agent = policy_agent or PolicyManagerAgent(blockchain=self.blockchain)
        withdraw_address = collector_address or self.checksum_address
        receipt = policy_agent.collect_policy_reward(collector_address=withdraw_address,
                                                     staker_address=self.checksum_address)
        return receipt

    @only_me
    @save_receipt
    def collect_staking_reward(self) -> str:
        """Withdraw tokens rewarded for staking."""
        receipt = self.staking_agent.collect_staking_reward(staker_address=self.checksum_address)
        return receipt

    @only_me
    @save_receipt
    def withdraw(self, amount: NU) -> str:
        """Withdraw tokens (assuming they're unlocked)"""
        receipt = self.staking_agent.withdraw(staker_address=self.checksum_address,
                                              amount=int(amount))
        return receipt


class Worker(NucypherTokenActor):
    """
    Ursula baseclass for blockchain operations, practically carrying a pickaxe.
    """

    class WorkerError(NucypherTokenActor.ActorError):
        pass

    class DetachedWorker(WorkerError):
        """Raised when the worker address is not assigned an on-chain stake in the StakingEscrow contract."""

    def __init__(self,
                 is_me: bool,
                 stake_tracker: StakeTracker = None,
                 worker_address: str = None,
                 start_working_loop: bool = True,
                 *args, **kwargs) -> None:

        super().__init__(*args, **kwargs)

        self.log = Logger("worker")

        self.__worker_address = worker_address
        self.is_me = is_me

        # Agency
        self.token_agent = NucypherTokenAgent(blockchain=self.blockchain)
        self.staking_agent = StakingEscrowAgent(blockchain=self.blockchain)

        # Stakes
        self.__start_time = WORKER_NOT_RUNNING
        self.__uptime_period = WORKER_NOT_RUNNING

        # Workers cannot be started without being assigned a stake first.
        if is_me:
            self.stake_tracker = stake_tracker or StakeTracker(checksum_addresses=[self.checksum_address])

            if not self.stake_tracker.stakes(checksum_address=self.checksum_address):
                raise self.DetachedWorker
            else:
                self.stake_tracker.add_action(self._confirm_period)
                if start_working_loop:
                    self.stake_tracker.start()

    @property
    def last_active_period(self) -> int:
        period = self.staking_agent.get_last_active_period(address=self.checksum_address)
        return period

    @only_me
    @save_receipt
    def confirm_activity(self) -> str:
        """For each period that the worker confirms activity, the staker is rewarded"""
        receipt = self.staking_agent.confirm_activity(worker_address=self.__worker_address)
        return receipt

    @only_me
    def _confirm_period(self) -> None:
        # TODO: Follow-up actions for downtime
        # TODO: Check for stake expiration and exit
        missed_periods = self.stake_tracker.current_period - self.last_active_period
        if missed_periods:
            self.log.warn(f"MISSED CONFIRMATIONS - {missed_periods} missed staking confirmations detected!")
        self.confirm_activity()  # < --- blockchain WRITE
        self.log.info("Confirmed activity for period {}".format(self.stake_tracker.current_period))


class PolicyAuthor(NucypherTokenActor):
    """Alice base class for blockchain operations, mocking up new policies!"""

    def __init__(self, checksum_address: str,
                 policy_agent: PolicyManagerAgent = None,
                 economics: TokenEconomics = None,
                 *args, **kwargs) -> None:
        """
        :param policy_agent: A policy agent with the blockchain attached;
                             If not passed, a default policy agent and blockchain connection will
                             be created from default values.

        """
        super().__init__(checksum_address=checksum_address, *args, **kwargs)

        # From defaults
        if not policy_agent:
            self.token_agent = NucypherTokenAgent(blockchain=self.blockchain)
            self.staking_agent = StakingEscrowAgent(blockchain=self.blockchain)
            self.policy_agent = PolicyManagerAgent(blockchain=self.blockchain)

        # Injected
        else:
            self.policy_agent = policy_agent

        self.economics = economics or TokenEconomics()

    def recruit(self, quantity: int, **options) -> List[str]:
        """
        Uses sampling logic to gather stakers from the blockchain and
        caches the resulting node ethereum addresses.

        :param quantity: Number of ursulas to sample from the blockchain.

        """
        staker_addresses = self.staking_agent.sample(quantity=quantity, **options)
        return staker_addresses

    def create_policy(self, *args, **kwargs):
        """
        Hence the name, a PolicyAuthor can create
        a BlockchainPolicy with themself as the author.

        :return: Returns a newly authored BlockchainPolicy with n proposed arrangements.

        """
        from nucypher.blockchain.eth.policies import BlockchainPolicy
        blockchain_policy = BlockchainPolicy(alice=self, *args, **kwargs)
        return blockchain_policy


class Investigator(NucypherTokenActor):
    """
    Actor that reports incorrect CFrags to the Adjudicator contract.
    In most cases, Bob will act as investigator, but the actor is generic enough than
    anyone can report CFrags.
    """

    def __init__(self,
                 checksum_address: str,
                 *args, **kwargs) -> None:

        super().__init__(checksum_address=checksum_address, *args, **kwargs)

        self.adjudicator_agent = AdjudicatorAgent(blockchain=self.blockchain)

    @save_receipt
    def request_evaluation(self, evidence):
        receipt = self.adjudicator_agent.evaluate_cfrag(evidence=evidence,
                                                        sender_address=self.checksum_address)
        return receipt

    def was_this_evidence_evaluated(self, evidence):
        return self.adjudicator_agent.was_this_evidence_evaluated(evidence=evidence)


class StakeHolder(BaseConfiguration):

    _NAME = 'stakeholder'
    TRANSACTION_GAS = {}

    class NoFundingAccount(BaseConfiguration.ConfigurationError):
        pass

    class NoStakes(BaseConfiguration.ConfigurationError):
        pass

    def __init__(self,
                 blockchain: BlockchainInterface,
                 sync_now: bool = True,
                 *args, **kwargs):

        super().__init__(*args, **kwargs)

        self.log = Logger(f"stakeholder")

        # Blockchain and Contract connection
        self.blockchain = blockchain
        self.staking_agent = StakingEscrowAgent(blockchain=blockchain)
        self.token_agent = NucypherTokenAgent(blockchain=blockchain)
        self.economics = TokenEconomics()

        # Mode
        self.connect(blockchain=blockchain)

        self.__accounts = list()
        self.__stakers = dict()
        self.__transacting_powers = dict()

        self.__get_accounts()

        if sync_now:
            self.read_onchain_stakes()  # Stakes

    #
    # Configuration
    #

    def static_payload(self) -> dict:
        """Values to read/write from stakeholder JSON configuration files"""
        payload = dict(provider_uri=self.blockchain.provider_uri,
                       blockchain=self.blockchain.to_dict(),
                       accounts=self.__accounts,
                       stakers=self.__serialize_stakers())
        return payload

    @classmethod
    def from_configuration_file(cls, filepath: str = None, sync_now: bool = True, **overrides) -> 'StakeHolder':
        filepath = filepath or cls.default_filepath()
        payload = cls._read_configuration_file(filepath=filepath)

        # Sub config
        blockchain_payload = payload.pop('blockchain')
        blockchain = BlockchainInterface.from_dict(payload=blockchain_payload)
        blockchain.connect(sync_now=sync_now)  # TODO: Leave this here?

        payload.update(dict(blockchain=blockchain))

        payload.update(overrides)
        instance = cls(filepath=filepath, **payload)
        return instance

    @validate_checksum_address
    def attach_transacting_power(self, checksum_address: str, password: str = None) -> None:
        try:
            transacting_power = self.__transacting_powers[checksum_address]
        except KeyError:
            transacting_power = TransactingPower(blockchain=self.blockchain,
                                                 password=password,
                                                 account=checksum_address)
            self.__transacting_powers[checksum_address] = transacting_power
        transacting_power.activate(password=password)

    def to_configuration_file(self, *args, **kwargs) -> str:
        filepath = super().to_configuration_file(*args, **kwargs)
        return filepath

    def connect(self, blockchain: BlockchainInterface = None) -> None:
        """Go Online"""
        if not self.staking_agent:
            self.staking_agent = StakingEscrowAgent(blockchain=blockchain)
        if not self.token_agent:
            self.token_agent = NucypherTokenAgent(blockchain=blockchain)
        self.blockchain = self.token_agent.blockchain

    #
    # Account Utilities
    #

    @property
    def accounts(self) -> list:
        return self.__accounts

    def __get_accounts(self) -> None:
        accounts = self.blockchain.client.accounts
        self.__accounts.extend(accounts)

    #
    # Staking Utilities
    #

    def read_onchain_stakes(self, account: str = None) -> None:
        if account:
            accounts = [account]
        else:
            accounts = self.__accounts

        for account in accounts:
            stakes = list(self.staking_agent.get_all_stakes(staker_address=account))
            if stakes:
                staker = Staker(is_me=True, checksum_address=account, blockchain=self.blockchain)
                self.__stakers[account] = staker

    @property
    def total_stake(self) -> NU:
        total = sum(staker.locked_tokens() for staker in self.stakers)
        return total

    @property
    def stakers(self) -> List[Staker]:
        return list(self.__stakers.values())

    @property
    def stakes(self) -> list:
        payload = list()
        for staker in self.__stakers.values():
            payload.extend(staker.stakes)
        return payload

    @property
    def account_balances(self) -> dict:
        balances = dict()
        for account in self.__accounts:
            funds = {'ETH': self.blockchain.client.get_balance(account),
                     'NU': self.token_agent.get_balance(account)}
            balances.update({account: funds})
        return balances

    @property
    def staker_balances(self) -> dict:
        balances = dict()
        for staker in self.stakers:
            staker_funds = {'ETH': staker.eth_balance, 'NU': staker.token_balance}
            balances[staker.checksum_address] = {staker.checksum_address: staker_funds}
        return balances

    def __serialize_stakers(self) -> list:
        payload = list()
        for staker in self.stakers:
            payload.append(staker.to_dict())
        return payload

    def get_active_staker(self, address: str) -> Staker:
        self.read_onchain_stakes(account=address)
        try:
            return self.__stakers[address]
        except KeyError:
            raise self.NoStakes(f"{address} does not have any stakes.")

    def create_worker_configuration(self,
                                    staking_address: str,
                                    worker_address: str,
                                    password: str,
                                    **configuration):

        """Generates a worker JSON configuration file for a given staking address."""
        from nucypher.config.characters import UrsulaConfiguration
        worker_configuration = UrsulaConfiguration.generate(checksum_address=staking_address,
                                                            worker_address=worker_address,
                                                            password=password,
                                                            config_root=self.config_root,
                                                            federated_only=False,
                                                            provider_uri=self.blockchain.provider_uri,
                                                            **configuration)
        return worker_configuration

    #
    # Actions
    #

    def set_worker(self, staker_address: str, worker_address: str, password: str = None):
        self.attach_transacting_power(checksum_address=staker_address, password=password)
        staker = self.get_active_staker(address=staker_address)
        receipt = self.staking_agent.set_worker(staker_address=staker.checksum_address,
                                               worker_address=worker_address)

        self.to_configuration_file(override=True)
        return receipt

    def initialize_stake(self,
                         amount: NU,
                         duration: int,
                         checksum_address: str,
                         password: str = None,
                         ) -> Stake:

        # Existing Staker address
        if not is_checksum_address(checksum_address):
            raise ValueError(f"{checksum_address} is an invalid EIP-55 checksum address.")

        try:
            staker = self.__stakers[checksum_address]
        except KeyError:
            if checksum_address not in self.__accounts:
                raise ValueError(f"{checksum_address} is an unknown wallet address.")
            else:
                staker = Staker(is_me=True, checksum_address=checksum_address, blockchain=self.blockchain)

        # Don the transacting power for the staker's account.
        self.attach_transacting_power(checksum_address=staker.checksum_address, password=password)
        new_stake = staker.initialize_stake(amount=amount, lock_periods=duration)

        # Update local cache and save to disk.
        self.__stakers[checksum_address] = staker
        staker.stake_tracker.refresh(checksum_addresses=[staker.checksum_address])
        self.to_configuration_file(override=True)

        return new_stake

    def divide_stake(self,
                     address: str,
                     index: int,
                     value: NU,
                     duration: int,
                     password: str = None,
                     ):

        staker = self.get_active_staker(address=address)
        if not staker.is_staking:
            raise Stake.StakingError(f"{staker.checksum_address} has no published stakes.")

        self.attach_transacting_power(checksum_address=staker.checksum_address, password=password)
        result = staker.divide_stake(stake_index=index,
                                     additional_periods=duration,
                                     target_value=value)

        # Save results to disk
        self.to_configuration_file(override=True)
        return result

    def calculate_rewards(self) -> dict:
        rewards = dict()
        for staker in self.stakers:
            reward = staker.calculate_reward()
            rewards[staker.checksum_address] = reward
        return rewards

    def collect_rewards(self,
                        staker_address: str,
                        password: str = None,
                        withdraw_address: str = None,
                        staking: bool = True,
                        policy: bool = True) -> Dict[str, dict]:

        if not staking and not policy:
            raise ValueError("Either staking or policy must be True in order to collect rewards")

        try:
            staker = self.get_active_staker(address=staker_address)
        except self.NoStakes:
            staker = Staker(is_me=True, checksum_address=staker_address, blockchain=self.blockchain)

        self.attach_transacting_power(checksum_address=staker.checksum_address, password=password)

        receipts = dict()
        if staking:
            receipts['staking_reward'] = staker.collect_staking_reward()
        if policy:
            receipts['policy_reward'] = staker.collect_policy_reward(collector_address=withdraw_address)

        self.to_configuration_file(override=True)
        return receipts
