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
    WORKER_NOT_RUNNING,
    NO_WORKER_ASSIGNED
)
from eth_tester.exceptions import TransactionFailed
from eth_utils import keccak, is_checksum_address
from twisted.logger import Logger

from nucypher.blockchain.economics import TokenEconomics, StandardTokenEconomics, TokenEconomicsFactory
from nucypher.blockchain.eth.agents import (
    NucypherTokenAgent,
    StakingEscrowAgent,
    PolicyManagerAgent,
    AdjudicatorAgent,
    ContractAgency)
from nucypher.blockchain.eth.deployers import (
    NucypherTokenDeployer,
    StakingEscrowDeployer,
    PolicyManagerDeployer,
    UserEscrowProxyDeployer,
    UserEscrowDeployer,
    AdjudicatorDeployer,
    BaseContractDeployer
)
from nucypher.blockchain.eth.interfaces import BlockchainDeployerInterface, BlockchainInterfaceFactory
from nucypher.blockchain.eth.interfaces import BlockchainInterface
from nucypher.blockchain.eth.registry import AllocationRegistry, BaseContractRegistry
from nucypher.blockchain.eth.token import NU, Stake, StakeList, WorkTracker
from nucypher.blockchain.eth.utils import datetime_to_period, calculate_period_duration, datetime_at_period
from nucypher.characters.control.emitters import StdoutEmitter
from nucypher.cli.painting import paint_contract_deployment
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

    def __init__(self, registry: BaseContractRegistry, checksum_address: str = None):

        # TODO: Consider this pattern - None for address?.
        # Note: If the base class implements multiple inheritance and already has a checksum address...
        try:
            parent_address = self.checksum_address  # type: str
            if checksum_address is not None:
                if parent_address != checksum_address:
                    raise ValueError("Can't have two different addresses.")
        except AttributeError:
            self.checksum_address = checksum_address  # type: str

        self.registry = registry
        self.token_agent = ContractAgency.get_agent(NucypherTokenAgent, registry=self.registry)
        self._saved_receipts = list()  # track receipts of transmitted transactions

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
        blockchain = BlockchainInterfaceFactory.get_interface()  # TODO: EthAgent?
        balance = blockchain.client.get_balance(self.checksum_address)
        return blockchain.client.w3.fromWei(balance, 'ether')

    @property
    def token_balance(self) -> NU:
        """Return this actors's current token balance"""
        balance = int(self.token_agent.get_balance(address=self.checksum_address))
        nu_balance = NU(balance, 'NuNit')
        return nu_balance


class ContractAdministrator(NucypherTokenActor):
    """
    The administrator of network contracts.
    """

    __interface_class = BlockchainDeployerInterface

    #
    # Deployer classes sorted by deployment dependency order.
    #

    standard_deployer_classes = (
        NucypherTokenDeployer,
    )

    dispatched_upgradeable_deployer_classes = (
        StakingEscrowDeployer,
        PolicyManagerDeployer,
        AdjudicatorDeployer,
    )

    upgradeable_deployer_classes = (
        *dispatched_upgradeable_deployer_classes,
        UserEscrowProxyDeployer,
    )

    ownable_deployer_classes = (*dispatched_upgradeable_deployer_classes, )

    deployer_classes = (*standard_deployer_classes,
                        *upgradeable_deployer_classes)

    class UnknownContract(ValueError):
        pass

    def __init__(self,
                 registry: BaseContractRegistry,
                 deployer_address: str = None,
                 client_password: str = None,
                 economics: TokenEconomics = None):
        """
        Note: super() is not called here to avoid setting the token agent.
        TODO: Review this logic ^^ "bare mode".
        """
        self.log = Logger("Deployment-Actor")

        self.deployer_address = deployer_address
        self.checksum_address = self.deployer_address
        self.economics = economics or StandardTokenEconomics()

        self.registry = registry
        self.user_escrow_deployers = dict()
        self.deployers = {d.contract_name: d for d in self.deployer_classes}

        self.transacting_power = TransactingPower(password=client_password, account=deployer_address)
        self.transacting_power.activate()

    def __repr__(self):
        r = '{name} - {deployer_address})'.format(name=self.__class__.__name__, deployer_address=self.deployer_address)
        return r

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
                        bare: bool = False,
                        progress=None,
                        *args, **kwargs,
                        ) -> Tuple[dict, BaseContractDeployer]:

        Deployer = self.__get_deployer(contract_name=contract_name)
        deployer = Deployer(registry=self.registry,
                            deployer_address=self.deployer_address,
                            economics=self.economics,
                            *args, **kwargs)

        if Deployer._upgradeable:
            is_initial_deployment = not bare
            if is_initial_deployment and not plaintext_secret:
                raise ValueError("An upgrade secret must be passed to perform initial deployment of a Dispatcher.")
            secret_hash = None
            if plaintext_secret:
                secret_hash = keccak(bytes(plaintext_secret, encoding='utf-8'))
            receipts = deployer.deploy(secret_hash=secret_hash,
                                       gas_limit=gas_limit,
                                       initial_deployment=is_initial_deployment,
                                       progress=progress)
        else:
            receipts = deployer.deploy(gas_limit=gas_limit, progress=progress)
        return receipts, deployer

    def upgrade_contract(self, contract_name: str, existing_plaintext_secret: str, new_plaintext_secret: str) -> dict:
        Deployer = self.__get_deployer(contract_name=contract_name)
        deployer = Deployer(registry=self.registry, deployer_address=self.deployer_address)
        new_secret_hash = keccak(bytes(new_plaintext_secret, encoding='utf-8'))
        receipts = deployer.upgrade(existing_secret_plaintext=bytes(existing_plaintext_secret, encoding='utf-8'),
                                    new_secret_hash=new_secret_hash)
        return receipts

    def retarget_proxy(self, contract_name: str, target_address: str, existing_plaintext_secret: str, new_plaintext_secret: str):
        Deployer = self.__get_deployer(contract_name=contract_name)
        deployer = Deployer(registry=self.registry, deployer_address=self.deployer_address)
        new_secret_hash = keccak(bytes(new_plaintext_secret, encoding='utf-8'))
        receipts = deployer.retarget(target_address=target_address,
                                     existing_secret_plaintext=bytes(existing_plaintext_secret, encoding='utf-8'),
                                     new_secret_hash=new_secret_hash)
        return receipts

    def rollback_contract(self, contract_name: str, existing_plaintext_secret: str, new_plaintext_secret: str):
        Deployer = self.__get_deployer(contract_name=contract_name)
        deployer = Deployer(registry=self.registry, deployer_address=self.deployer_address)
        new_secret_hash = keccak(bytes(new_plaintext_secret, encoding='utf-8'))
        receipts = deployer.rollback(existing_secret_plaintext=bytes(existing_plaintext_secret, encoding='utf-8'),
                                     new_secret_hash=new_secret_hash)
        return receipts

    def deploy_user_escrow(self, allocation_registry: AllocationRegistry) -> UserEscrowDeployer:
        user_escrow_deployer = UserEscrowDeployer(registry=self.registry,
                                                  deployer_address=self.deployer_address,
                                                  allocation_registry=allocation_registry)
        user_escrow_deployer.deploy()
        principal_address = user_escrow_deployer.contract.address
        self.user_escrow_deployers[principal_address] = user_escrow_deployer
        return user_escrow_deployer

    def deploy_network_contracts(self,
                                 secrets: dict,
                                 interactive: bool = True,
                                 emitter: StdoutEmitter = None,
                                 etherscan: bool = False) -> dict:
        """

        :param secrets: Contract upgrade secrets dictionary
        :param interactive: If True, wait for keypress after each contract deployment
        :param emitter: A console output emitter instance. If emitter is None, no output will be echoed to the console.
        :param etherscan: Open deployed contracts in Etherscan
        :return: Returns a dictionary of deployment receipts keyed by contract name
        """

        if interactive and not emitter:
            raise ValueError("'emitter' is a required keyword argument when interactive is True.")

        deployment_receipts = dict()
        gas_limit = None  # TODO: Gas management

        # deploy contracts
        total_deployment_transactions = 0
        for deployer_class in self.deployer_classes:
            total_deployment_transactions += len(deployer_class.deployment_steps)

        first_iteration = True
        with click.progressbar(length=total_deployment_transactions,
                               label="Deployment progress",
                               show_eta=False) as bar:
            bar.short_limit = 0
            for deployer_class in self.deployer_classes:
                if interactive and not first_iteration:
                    click.pause(info=f"\nPress any key to continue with deployment of {deployer_class.contract_name}")

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
                    blockchain = BlockchainInterfaceFactory.get_interface()
                    paint_contract_deployment(contract_name=deployer_class.contract_name,
                                              receipts=receipts,
                                              contract_address=deployer.contract_address,
                                              emitter=emitter,
                                              chain_name=blockchain.client.chain_name,
                                              open_in_browser=etherscan)

                deployment_receipts[deployer_class.contract_name] = receipts
                first_iteration = False

        return deployment_receipts

    def relinquish_ownership(self,
                             new_owner: str,
                             emitter: StdoutEmitter = None,
                             interactive: bool = True,
                             transaction_gas_limit: int = None) -> dict:

        if not is_checksum_address(new_owner):
            raise ValueError(f"{new_owner} is an invalid EIP-55 checksum address.")

        receipts = dict()

        for contract_deployer in self.ownable_deployer_classes:
            deployer = contract_deployer(registry=self.registry, deployer_address=self.deployer_address)
            deployer.transfer_ownership(new_owner=new_owner, transaction_gas_limit=transaction_gas_limit)

            if emitter:
                emitter.echo(f"Transferred ownership of {deployer.contract_name} to {new_owner}")

            if interactive:
                click.pause(info="Press any key to continue")

            receipts[contract_deployer.contract_name] = receipts

        return receipts

    def deploy_beneficiary_contracts(self,
                                     allocations: List[Dict[str, Union[str, int]]],
                                     allocation_outfile: str = None,
                                     allocation_registry: AllocationRegistry = None,
                                     crash_on_failure: bool = True,
                                     ) -> Dict[str, dict]:
        """

        Example allocation dataset (one year is 31536000 seconds):

        data = [{'beneficiary_address': '0xdeadbeef', 'amount': 100, 'duration_seconds': 31536000},
                {'beneficiary_address': '0xabced120', 'amount': 133432, 'duration_seconds': 31536000*2},
                {'beneficiary_address': '0xf7aefec2', 'amount': 999, 'duration_seconds': 31536000*3}]
        """
        if allocation_registry and allocation_outfile:
            raise self.ActorError("Pass either allocation registry or allocation_outfile, not both.")
        if allocation_registry is None:
            allocation_registry = AllocationRegistry(filepath=allocation_outfile)

        allocation_txhashes, failed = dict(), list()
        for allocation in allocations:
            deployer = self.deploy_user_escrow(allocation_registry=allocation_registry)

            try:
                txhashes = deployer.deliver(value=allocation['amount'],
                                            duration=allocation['duration_seconds'],
                                            beneficiary_address=allocation['beneficiary_address'])
            except TransactionFailed:
                if crash_on_failure:
                    raise
                self.log.debug(f"Failed allocation transaction for {allocation['amount']} to {allocation['beneficiary_address']}")
                failed.append(allocation)
                continue

            else:
                allocation_txhashes[allocation['beneficiary_address']] = txhashes

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

    def __init__(self, is_me: bool, *args, **kwargs) -> None:

        super().__init__(*args, **kwargs)
        self.log = Logger("staker")

        self.is_me = is_me
        self.__worker_address = None

        # Blockchain
        self.policy_agent = ContractAgency.get_agent(PolicyManagerAgent, registry=self.registry)
        self.staking_agent = ContractAgency.get_agent(StakingEscrowAgent, registry=self.registry)
        self.economics = TokenEconomicsFactory.get_economics(registry=self.registry)
        self.stakes = StakeList(registry=self.registry, checksum_address=self.checksum_address)

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
    def is_staking(self) -> bool:
        """Checks if this Staker currently has active stakes / locked tokens."""
        self.stakes.refresh()
        return bool(self.stakes)

    def locked_tokens(self, periods: int = 0) -> NU:
        """Returns the amount of tokens this staker has locked for a given duration in periods."""
        self.stakes.refresh()
        raw_value = self.staking_agent.get_locked_tokens(staker_address=self.checksum_address, periods=periods)
        value = NU.from_nunits(raw_value)
        return value

    @property
    def current_stake(self) -> NU:
        """
        The total number of staked tokens, either locked or unlocked in the current period.
        """
        stake = self.staking_agent.owned_tokens(staker_address=self.checksum_address)
        nu_stake = NU.from_nunits(stake)
        return nu_stake

    @only_me
    def divide_stake(self,
                     stake_index: int,
                     target_value: NU,
                     additional_periods: int = None,
                     expiration: maya.MayaDT = None) -> tuple:

        # Calculate duration in periods
        if additional_periods and expiration:
            raise ValueError("Pass the number of lock periods or an expiration MayaDT; not both.")

        # Update staking cache element
        stakes = self.stakes

        # Select stake to divide from local cache
        try:
            current_stake = stakes[stake_index]
        except KeyError:
            if len(stakes):
                message = f"Cannot divide stake - No stake exists with index {stake_index}."
            else:
                message = "Cannot divide stake - There are no active stakes."
            raise Stake.StakingError(message)

        # Calculate stake duration in periods
        if expiration:
            additional_periods = datetime_to_period(datetime=expiration, seconds_per_period=self.economics.seconds_per_period) - current_stake.final_locked_period
            if additional_periods <= 0:
                raise Stake.StakingError(f"New expiration {expiration} must be at least 1 period from the "
                                         f"current stake's end period ({current_stake.final_locked_period}).")

        # Do it already!
        modified_stake, new_stake = current_stake.divide(target_value=target_value,
                                                         additional_periods=additional_periods)

        # Update staking cache element
        self.stakes.refresh()

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
            lock_periods = calculate_period_duration(future_time=expiration,
                                                     seconds_per_period=self.economics.seconds_per_period)

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
            raise Stake.StakingError(f"Cannot initialize stake - "
                                     f"Maximum stake value exceeded for {self.checksum_address} "
                                     f"with a target value of {amount}.")

        # Write to blockchain
        new_stake = Stake.initialize_stake(staker=self,
                                           amount=amount,
                                           lock_periods=lock_periods)

        # Update staking cache element
        self.stakes.refresh()

        return new_stake

    @property
    def is_restaking(self) -> bool:
        restaking = self.staking_agent.is_restaking(staker_address=self.checksum_address)
        return restaking

    @only_me
    @save_receipt
    def enable_restaking(self) -> dict:
        receipt = self.staking_agent.set_restaking(staker_address=self.checksum_address, value=True)
        return receipt

    @only_me
    @save_receipt
    def enable_restaking_lock(self, release_period: int):
        current_period = self.staking_agent.get_current_period()
        if release_period < current_period:
            raise ValueError(f"Terminal restaking period must be in the future.  "
                             f"Current period is {current_period}, got '{release_period}'.")
        receipt = self.staking_agent.lock_restaking(staker_address=self.checksum_address,
                                                    release_period=release_period)
        return receipt

    @property
    def restaking_lock_enabled(self) -> bool:
        status = self.staking_agent.is_restaking_locked(staker_address=self.checksum_address)
        return status

    def disable_restaking(self) -> dict:
        receipt = self.staking_agent.set_restaking(staker_address=self.checksum_address, value=False)
        return receipt
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
    def collect_policy_reward(self, collector_address=None) -> dict:
        """Collect rewarded ETH."""
        withdraw_address = collector_address or self.checksum_address
        receipt = self.policy_agent.collect_policy_reward(collector_address=withdraw_address,
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
        """Raised when the Worker is not bonded to a Staker in the StakingEscrow contract."""

    def __init__(self,
                 is_me: bool,
                 work_tracker: WorkTracker = None,
                 worker_address: str = None,
                 start_working_now: bool = True,
                 confirm_now: bool = True,
                 check_active_worker: bool = True,
                 *args, **kwargs):

        super().__init__(*args, **kwargs)
        self.log = Logger("worker")

        self.__worker_address = worker_address
        self.is_me = is_me

        # Agency
        self.staking_agent = ContractAgency.get_agent(StakingEscrowAgent, registry=self.registry)

        # Stakes
        self.__start_time = WORKER_NOT_RUNNING
        self.__uptime_period = WORKER_NOT_RUNNING

        # Workers cannot be started without being assigned a stake first.
        if is_me:
            self.stakes = StakeList(registry=self.registry, checksum_address=self.checksum_address)
            self.stakes.refresh()
            if check_active_worker and not len(self.stakes):
                raise self.DetachedWorker(f"{self.__worker_address} is not bonded to {self.checksum_address}.")

            self.work_tracker = work_tracker or WorkTracker(worker=self)
            if start_working_now:
                self.work_tracker.start(act_now=False)

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


class BlockchainPolicyAuthor(NucypherTokenActor):
    """Alice base class for blockchain operations, mocking up new policies!"""

    def __init__(self,
                 checksum_address: str,
                 rate: int = None,
                 duration_periods: int = None,
                 first_period_reward: int = None,
                 *args, **kwargs):
        """
        :param policy_agent: A policy agent with the blockchain attached;
                             If not passed, a default policy agent and blockchain connection will
                             be created from default values.

        """
        super().__init__(checksum_address=checksum_address, *args, **kwargs)

        # From defaults
        self.staking_agent = ContractAgency.get_agent(StakingEscrowAgent, registry=self.registry)
        self.policy_agent = ContractAgency.get_agent(PolicyManagerAgent, registry=self.registry)

        self.economics = TokenEconomicsFactory.get_economics(registry=self.registry)
        self.rate = rate
        self.duration_periods = duration_periods
        self.first_period_reward = first_period_reward

        policy_value_specified = self.rate and self.first_period_reward
        if policy_value_specified and self.first_period_reward >= self.rate:
            raise ValueError(f"Policy rate of ({self.rate}) per period must be greater "
                             f"than the first period rate of ({self.first_period_reward})")

    def generate_policy_parameters(self,
                                   number_of_ursulas: int = None,
                                   duration_periods: int = None,
                                   expiration: maya.MayaDT = None,
                                   value: int = None,
                                   rate: int = None,
                                   first_period_reward: int = None,
                                   ) -> dict:
        """
        Construct policy creation from parameters or overrides.
        """

        if not duration_periods and not expiration:
            raise ValueError("Policy end time must be specified as 'expiration' or 'duration_periods', got neither.")

        # Merge injected and default params.
        first_period_reward = first_period_reward or self.first_period_reward
        rate = rate or self.rate
        duration_periods = duration_periods or self.duration_periods

        # Calculate duration in periods and expiration datetime
        if expiration:
            duration_periods = calculate_period_duration(future_time=expiration,
                                                         seconds_per_period=self.economics.seconds_per_period)
        else:
            duration_periods = duration_periods or self.duration_periods
            expiration = datetime_at_period(self.staking_agent.get_current_period() + duration_periods,
                                            seconds_per_period=self.economics.seconds_per_period)

        from nucypher.policy.policies import BlockchainPolicy
        blockchain_payload = BlockchainPolicy.generate_policy_parameters(n=number_of_ursulas,
                                                                         duration_periods=duration_periods,
                                                                         first_period_reward=first_period_reward,
                                                                         value=value,
                                                                         rate=rate)

        # These values may have been recalculated in this block.
        policy_end_time = dict(duration_periods=duration_periods, expiration=expiration)
        payload = {**blockchain_payload, **policy_end_time}
        return payload

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
        Hence the name, a BlockchainPolicyAuthor can create
        a BlockchainPolicy with themself as the author.

        :return: Returns a newly authored BlockchainPolicy with n proposed arrangements.

        """
        from nucypher.policy.policies import BlockchainPolicy
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
        self.adjudicator_agent = ContractAgency.get_agent(AdjudicatorAgent, registry=self.registry)

    @save_receipt
    def request_evaluation(self, evidence):
        receipt = self.adjudicator_agent.evaluate_cfrag(evidence=evidence,
                                                        sender_address=self.checksum_address)
        return receipt

    def was_this_evidence_evaluated(self, evidence):
        return self.adjudicator_agent.was_this_evidence_evaluated(evidence=evidence)
