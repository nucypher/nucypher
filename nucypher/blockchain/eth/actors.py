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

import csv
import json
import os
import sys
import time
from decimal import Decimal
from web3.types import TxReceipt
import traceback
import click
import maya
from eth_tester.exceptions import TransactionFailed as TestTransactionFailed
from eth_utils import to_canonical_address, to_checksum_address
from typing import Dict, Iterable, List, Optional, Tuple
from web3 import Web3
from web3.exceptions import ValidationError

from constant_sorrow.constants import FULL, NO_WORKER_BONDED, WORKER_NOT_RUNNING
from nucypher.acumen.nicknames import nickname_from_seed
from nucypher.blockchain.economics import BaseEconomics, EconomicsFactory, StandardTokenEconomics
from nucypher.blockchain.eth.agents import (
    AdjudicatorAgent,
    ContractAgency,
    MultiSigAgent,
    NucypherTokenAgent,
    PolicyManagerAgent,
    PreallocationEscrowAgent,
    StakingEscrowAgent,
    WorkLockAgent
)
from nucypher.blockchain.eth.constants import NULL_ADDRESS
from nucypher.blockchain.eth.decorators import (
    only_me,
    save_receipt,
    validate_checksum_address
)
from nucypher.blockchain.eth.deployers import (
    AdjudicatorDeployer,
    BaseContractDeployer,
    MultiSigDeployer,
    NucypherTokenDeployer,
    PolicyManagerDeployer,
    StakingEscrowDeployer,
    StakingInterfaceDeployer,
    StakingInterfaceRouterDeployer,
    WorklockDeployer
)
from nucypher.blockchain.eth.interfaces import BlockchainDeployerInterface, BlockchainInterfaceFactory
from nucypher.blockchain.eth.multisig import Authorization, Proposal
from nucypher.blockchain.eth.registry import BaseContractRegistry, IndividualAllocationRegistry
from nucypher.blockchain.eth.signers import KeystoreSigner, Signer, Web3Signer
from nucypher.blockchain.eth.token import NU, Stake, StakeList, WorkTracker, validate_prolong, validate_increase, \
    validate_divide
from nucypher.blockchain.eth.utils import (
    calculate_period_duration,
    datetime_at_period,
    datetime_to_period,
    prettify_eth_amount
)
from nucypher.characters.banners import STAKEHOLDER_BANNER
from nucypher.characters.control.emitters import StdoutEmitter
from nucypher.cli.painting.deployment import paint_contract_deployment, paint_input_allocation_file
from nucypher.cli.painting.transactions import paint_receipt_summary
from nucypher.config.constants import DEFAULT_CONFIG_ROOT
from nucypher.crypto.powers import TransactingPower
from nucypher.types import NuNits, Period
from nucypher.utilities.logging import Logger


class BaseActor:
    """
    Concrete base class for any actor that will interface with NuCypher's ethereum smart contracts.
    """

    class ActorError(Exception):
        pass

    @validate_checksum_address
    def __init__(self, registry: BaseContractRegistry, domains=None, checksum_address: str = None):

        # TODO: Consider this pattern - None for address?.  #1507
        # Note: If the base class implements multiple inheritance and already has a checksum address...
        try:
            parent_address = self.checksum_address  # type: str
            if checksum_address is not None:
                if parent_address != checksum_address:
                    raise ValueError("Can't have two different addresses.")
        except AttributeError:
            self.checksum_address = checksum_address  # type: str

        self.registry = registry
        if domains:  # StakeHolder config inherits from character config, which has 'domains' - #1580
            self.network = list(domains)[0]

        self._saved_receipts = list()  # track receipts of transmitted transactions

    def __repr__(self):
        class_name = self.__class__.__name__
        r = "{}(address='{}')"
        r = r.format(class_name, self.checksum_address)
        return r

    def __eq__(self, other) -> bool:
        """Actors are equal if they have the same address."""
        try:
            return bool(self.checksum_address == other.checksum_address)
        except AttributeError:
            return False

    @property
    def eth_balance(self) -> Decimal:
        """Return this actors's current ETH balance"""
        blockchain = BlockchainInterfaceFactory.get_interface()  # TODO: EthAgent?  #1509
        balance = blockchain.client.get_balance(self.checksum_address)
        return Web3.fromWei(balance, 'ether')


class NucypherTokenActor(BaseActor):
    """
    Actor to interface with the NuCypherToken contract
    """

    def __init__(self, registry: BaseContractRegistry, **kwargs):
        super().__init__(registry, **kwargs)
        self.token_agent = ContractAgency.get_agent(NucypherTokenAgent, registry=self.registry)

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
    # Deployer Registry
    #

    # Note: Deployer classes are sorted by deployment dependency order.

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
        StakingInterfaceDeployer,
    )

    aux_deployer_classes = (
        WorklockDeployer,
        MultiSigDeployer,
    )

    # For ownership transfers.
    ownable_deployer_classes = (*dispatched_upgradeable_deployer_classes,
                                StakingInterfaceRouterDeployer,
                                )

    # Used in the automated deployment series.
    primary_deployer_classes = (*standard_deployer_classes,
                                *upgradeable_deployer_classes)

    # Comprehensive collection.
    all_deployer_classes = (*primary_deployer_classes,
                            *aux_deployer_classes)

    class UnknownContract(ValueError):
        pass

    def __init__(self,
                 registry: BaseContractRegistry,
                 deployer_address: str = None,
                 client_password: str = None,
                 signer: Signer = None,
                 staking_escrow_test_mode: bool = False,
                 is_transacting: bool = True,  # FIXME: Workaround to be able to build MultiSig TXs
                 economics: BaseEconomics = None):
        """
        Note: super() is not called here to avoid setting the token agent.  TODO: call super but use "bare mode" without token agent.  #1510
        """
        self.log = Logger("Deployment-Actor")

        self.deployer_address = deployer_address
        self.checksum_address = self.deployer_address
        self.economics = economics or StandardTokenEconomics()
        self.staking_escrow_test_mode = staking_escrow_test_mode

        self.registry = registry
        self.preallocation_escrow_deployers = dict()
        self.deployers = {d.contract_name: d for d in self.all_deployer_classes}

        # Powers
        if is_transacting:
            self.deployer_power = TransactingPower(signer=signer,
                                                   password=client_password,
                                                   account=deployer_address,
                                                   cache=True)
            self.transacting_power = self.deployer_power
            self.transacting_power.activate()
        else:
            self.deployer_power = None
            self.transacting_power = None

        self.sidekick_power = None
        self.sidekick_address = None

    def __repr__(self):
        r = '{name} - {deployer_address})'.format(name=self.__class__.__name__, deployer_address=self.deployer_address)
        return r

    @validate_checksum_address
    def recruit_sidekick(self, sidekick_address: str, sidekick_password: str):
        self.sidekick_power = TransactingPower(account=sidekick_address, password=sidekick_password, cache=True)
        if self.sidekick_power.is_device:
            raise ValueError("Holy Wallet! Sidekicks can only be SW accounts")
        self.sidekick_address = sidekick_address

    def activate_deployer(self, refresh: bool = True):
        if not self.deployer_power.is_active:
            self.transacting_power = self.deployer_power
            self.transacting_power.activate()
        elif refresh:
            self.transacting_power.activate()

    def activate_sidekick(self, refresh: bool = True):
        if not self.sidekick_power:
            raise TransactingPower.not_found_error
        elif not self.sidekick_power.is_active:
            self.transacting_power = self.sidekick_power
            self.transacting_power.activate()
        elif refresh:
            self.transacting_power.activate()

    def __get_deployer(self, contract_name: str):
        try:
            Deployer = self.deployers[contract_name]
        except KeyError:
            raise self.UnknownContract(contract_name)
        return Deployer

    def deploy_contract(self,
                        contract_name: str,
                        gas_limit: int = None,
                        deployment_mode=FULL,
                        ignore_deployed: bool = False,
                        progress=None,
                        confirmations: int = 0,
                        deployment_parameters: dict = None,
                        emitter=None,
                        *args, **kwargs,
                        ) -> Tuple[dict, BaseContractDeployer]:

        deployment_parameters = deployment_parameters or {}

        Deployer = self.__get_deployer(contract_name=contract_name)
        if Deployer is StakingEscrowDeployer:
            kwargs.update({"test_mode": self.staking_escrow_test_mode})

        deployer = Deployer(registry=self.registry,
                            deployer_address=self.deployer_address,
                            economics=self.economics,
                            *args, **kwargs)

        self.transacting_power.activate()  # Activate the TransactingPower in case too much time has passed
        if Deployer._upgradeable:
            receipts = deployer.deploy(gas_limit=gas_limit,
                                       progress=progress,
                                       ignore_deployed=ignore_deployed,
                                       confirmations=confirmations,
                                       deployment_mode=deployment_mode,
                                       emitter=emitter,
                                       **deployment_parameters)
        else:
            receipts = deployer.deploy(gas_limit=gas_limit,
                                       progress=progress,
                                       confirmations=confirmations,
                                       deployment_mode=deployment_mode,
                                       ignore_deployed=ignore_deployed,
                                       emitter=emitter,
                                       **deployment_parameters)
        return receipts, deployer

    def upgrade_contract(self,
                         contract_name: str,
                         ignore_deployed: bool = False
                         ) -> dict:
        Deployer = self.__get_deployer(contract_name=contract_name)
        deployer = Deployer(registry=self.registry, deployer_address=self.deployer_address)
        receipts = deployer.upgrade(ignore_deployed=ignore_deployed)
        return receipts

    def retarget_proxy(self,
                       contract_name: str,
                       target_address: str,
                       just_build_transaction: bool = False):
        Deployer = self.__get_deployer(contract_name=contract_name)
        deployer = Deployer(registry=self.registry, deployer_address=self.deployer_address)
        result = deployer.retarget(target_address=target_address,
                                   just_build_transaction=just_build_transaction)
        return result

    def rollback_contract(self, contract_name: str):
        Deployer = self.__get_deployer(contract_name=contract_name)
        deployer = Deployer(registry=self.registry, deployer_address=self.deployer_address)
        receipts = deployer.rollback()
        return receipts

    def deploy_network_contracts(self,
                                 interactive: bool = True,
                                 emitter: StdoutEmitter = None,
                                 etherscan: bool = False,
                                 ignore_deployed: bool = False) -> dict:
        """

        :param interactive: If True, wait for keypress after each contract deployment
        :param emitter: A console output emitter instance. If emitter is None, no output will be echoed to the console.
        :param etherscan: Open deployed contracts in Etherscan
        :param ignore_deployed: Ignore already deployed contracts if exist
        :return: Returns a dictionary of deployment receipts keyed by contract name
        """

        if interactive and not emitter:
            raise ValueError("'emitter' is a required keyword argument when interactive is True.")

        deployment_receipts = dict()
        gas_limit = None  # TODO: Gas management - #842

        # deploy contracts
        total_deployment_transactions = 0
        for deployer_class in self.primary_deployer_classes:
            total_deployment_transactions += len(deployer_class.deployment_steps)

        first_iteration = True
        with click.progressbar(length=total_deployment_transactions,
                               label="Deployment progress",
                               show_eta=False) as bar:
            bar.short_limit = 0
            for deployer_class in self.primary_deployer_classes:
                if interactive and not first_iteration:
                    click.pause(info=f"\nPress any key to continue with deployment of {deployer_class.contract_name}")

                if emitter:
                    emitter.echo(f"\nDeploying {deployer_class.contract_name} ...")
                    bar._last_line = None
                    bar.render_progress()

                if deployer_class in self.standard_deployer_classes:
                    receipts, deployer = self.deploy_contract(contract_name=deployer_class.contract_name,
                                                              gas_limit=gas_limit,
                                                              progress=bar,
                                                              emitter=emitter)
                else:
                    receipts, deployer = self.deploy_contract(contract_name=deployer_class.contract_name,
                                                              gas_limit=gas_limit,
                                                              progress=bar,
                                                              ignore_deployed=ignore_deployed,
                                                              emitter=emitter)

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

    def batch_deposits(self,
                       allocation_data_filepath: str,
                       interactive: bool = True,
                       emitter: StdoutEmitter = None,
                       gas_limit: int = None
                       ) -> Dict[str, dict]:
        """
        The allocations file is a JSON or CSV file containing a list of substakes.
        Each substake is comprised of a staker address, an amount of tokens locked (in NuNits),
        and a lock duration (in periods).

        It accepts both CSV and JSON formats. Example allocation file in CSV format:

        "checksum_address","amount","lock_periods"
        "0xFABADA",123456,30
        "0xFABADA",789,45

        Example allocation file in JSON format:

        [ {"checksum_address": "0xFABADA", "amount": 123456, "lock_periods": 30},
          {"checksum_address": "0xFABADA", "amount": 789, "lock_periods": 45}]
        """

        if interactive and not emitter:
            raise ValueError("'emitter' is a required keyword argument when interactive is True.")

        allocator = Allocator(allocation_data_filepath, self.registry, self.deployer_address)

        # TODO: Check validity of input address (check TX)

        if emitter:
            blockchain = BlockchainInterfaceFactory.get_interface()
            chain_name = blockchain.client.chain_name
            paint_input_allocation_file(emitter, allocator.allocations)

        if interactive:
            click.confirm("Continue with the allocations process?", abort=True)

        batch_deposit_receipts, failed = dict(), False
        with click.progressbar(length=len(allocator.allocations),
                               label="Allocation progress",
                               show_eta=False) as bar:

            while allocator.pending_deposits and not failed:

                self.activate_deployer(refresh=True)

                try:
                    deposited_stakers, receipt = allocator.deposit_next_batch(sender_address=self.deployer_address,
                                                                              gas_limit=gas_limit)
                except (TestTransactionFailed, ValidationError, ValueError):  # TODO: 1950
                    if emitter:
                        emitter.echo(f"\nFailed to deploy next batch. These addresses weren't funded:", color="yellow")
                        for staker in allocator.pending_deposits:
                            emitter.echo(f"\t{staker}", color="yellow")
                        emitter.echo(f"\nThe failure is caused by the following exception:")

                    for line in traceback.format_exception(*sys.exc_info()):
                        emitter.echo(line, color='red')
                    failed = True
                else:
                    number_of_deposits = len(deposited_stakers)
                    if emitter:
                        emitter.echo(f"\nDeployed allocations for {number_of_deposits} stakers:")
                        for staker in deposited_stakers:
                            emitter.echo(f"\t{staker}")
                        emitter.echo()
                        bar._last_line = None
                        bar.render_progress()

                    bar.update(number_of_deposits)

                    if emitter:
                        emitter.echo()
                        paint_receipt_summary(emitter=emitter,
                                              receipt=receipt,
                                              chain_name=chain_name,
                                              transaction_type=f'batch_deposit_{number_of_deposits}_stakers')

                    batch_deposit_receipts.update({staker: {'batch_deposit': receipt} for staker in deposited_stakers})

                    if interactive:
                        click.pause(info=f"\nPress any key to continue with next batch of allocations")

        return batch_deposit_receipts

    def save_deployment_receipts(self, receipts: dict, filename_prefix: str = 'deployment') -> str:
        config_root = DEFAULT_CONFIG_ROOT  # We force the use of the default here.
        filename = f'{filename_prefix}-receipts-{self.deployer_address[:6]}-{maya.now().epoch}.json'
        filepath = os.path.join(config_root, filename)
        os.makedirs(config_root, exist_ok=True)
        with open(filepath, 'w') as file:
            data = dict()
            for contract_name, contract_receipts in receipts.items():
                contract_records = dict()
                for tx_name, receipt in contract_receipts.items():
                    # Formatting
                    pretty_receipt = {item: str(result) for item, result in receipt.items()}
                    contract_records[tx_name] = pretty_receipt
                data[contract_name] = contract_records
            data = json.dumps(data, indent=4)
            file.write(data)
        return filepath

    def set_fee_rate_range(self,
                           minimum: int,
                           default: int,
                           maximum: int,
                           transaction_gas_limit: int = None) -> TxReceipt:

        policy_manager_deployer = PolicyManagerDeployer(registry=self.registry,
                                                        deployer_address=self.deployer_address,
                                                        economics=self.economics)
        receipt = policy_manager_deployer.set_fee_rate_range(minimum=minimum,
                                                             default=default,
                                                             maximum=maximum,
                                                             gas_limit=transaction_gas_limit)
        return receipt


class Allocator:
    class AllocationInputError(Exception):
        """Raised when the allocation data file doesn't have the correct format"""

    OCCUPATION_RATIO = 0.9  # When there's no explicit gas limit, we'll try to use the block limit up to this ratio

    def __init__(self, filepath: str, registry, deployer_address):

        self.log = Logger("allocator")
        self.staking_agent = ContractAgency.get_agent(StakingEscrowAgent,
                                                      registry=registry)  # type: StakingEscrowAgent
        self.max_substakes = self.staking_agent.contract.functions.MAX_SUB_STAKES().call()
        self.allocations = dict()
        self.deposited = set()
        self.economics = EconomicsFactory.get_economics(registry)

        self.__total_to_allocate = 0
        self.__process_allocation_data(str(filepath))
        self.__approve_token_transfer(registry, deployer_address)

    def __process_allocation_data(self, filepath: str):
        try:
            with open(filepath, 'r') as allocation_file:
                if filepath.endswith(".csv"):
                    reader = csv.DictReader(allocation_file)
                    allocation_data = list(reader)
                else:  # Assume it's JSON by default
                    allocation_data = json.load(allocation_file)
        except FileNotFoundError:
            raise self.AllocationInputError(f"No allocation data file found at {filepath}")

        # Pre-process allocations data
        for entry in allocation_data:
            try:
                staker = to_checksum_address(entry['checksum_address'])
                amount = int(entry['amount'])
                lock_periods = int(entry['lock_periods'])
            except (KeyError, ValueError) as e:
                raise self.AllocationInputError(f"Invalid allocation data: {str(e)}")
            else:
                self._add_substake(staker, amount, lock_periods)
                self.__total_to_allocate += amount

    def __approve_token_transfer(self, registry, deployer_address):
        token_agent = ContractAgency.get_agent(NucypherTokenAgent, registry=registry)  # type: NucypherTokenAgent

        balance = token_agent.get_balance(deployer_address)
        if balance < self.__total_to_allocate:
            raise ValueError(f"Not enough tokens to allocate."
                             f"We need at least {NU.from_nunits(self.__total_to_allocate)}.")

        allowance = token_agent.get_allowance(owner=deployer_address, spender=self.staking_agent.contract_address)
        if allowance < self.__total_to_allocate:
            self.log.debug(f"Allocating a total of {NU.from_nunits(self.__total_to_allocate)}")
            _allowance_receipt = token_agent.increase_allowance(sender_address=deployer_address,
                                                                spender_address=self.staking_agent.contract_address,
                                                                increase=NuNits(self.__total_to_allocate - allowance))

    def _add_substake(self, staker, amount, lock_periods):
        try:
            substakes = self.allocations[staker]
            if len(substakes) >= self.max_substakes:
                raise ValueError(f"Number of sub-stakes, {len(substakes)}, must be ≤ {self.max_substakes}")
        except KeyError:
            if list(self.staking_agent.get_all_stakes(staker_address=staker)):
                raise ValueError(f"{staker} is already a staker. It cannot be included in a batch deposit")
            substakes = list()
            self.allocations[staker] = substakes

        message = f"Invalid substake for {staker}: "
        if amount < self.economics.minimum_allowed_locked:
            message += f"Amount ({amount}) is below the min allowed ({self.economics.minimum_allowed_locked})"
            raise ValueError(message)
        overall_amount = sum([amount for amount, periods in substakes])
        if overall_amount + amount > self.economics.maximum_allowed_locked:
            message += f"Total amount is above the max allowed ({self.economics.maximum_allowed_locked})"
            raise ValueError(message)
        if lock_periods < self.economics.minimum_locked_periods:
            message += f"Lock periods ({lock_periods}) are below the min ({self.economics.minimum_locked_periods})"
            raise ValueError(message)

        substakes.append((amount, lock_periods))

    def deposit_next_batch(self,
                           sender_address: str,
                           gas_limit: int = None) -> Tuple[List[str], dict]:

        pending_stakers = self.pending_deposits

        self.log.debug(f"Constructing next batch. "
                       f"Currently, {len(pending_stakers)} stakers pending, {len(self.deposited)} deposited.")

        batch_size = 1
        if not gas_limit:
            block_limit = self.staking_agent.blockchain.client.w3.eth.getBlock(block_identifier='latest').gasLimit
            gas_limit = int(self.OCCUPATION_RATIO * block_limit)
        self.log.debug(f"Gas limit for this batch is {gas_limit}")

        # Execute a dry-run of the batch deposit method, incrementing the batch size, until it's too big and fails.
        last_good_batch = None
        while batch_size <= len(pending_stakers):
            test_batch = {staker: self.allocations[staker] for staker in pending_stakers[:batch_size]}
            batch_parameters = self.staking_agent.construct_batch_deposit_parameters(deposits=test_batch)
            try:
                estimated_gas = self.staking_agent.batch_deposit(*batch_parameters,
                                                                 sender_address=sender_address,
                                                                 dry_run=True,
                                                                 gas_limit=gas_limit)
            except (TestTransactionFailed, ValidationError, ValueError):  # TODO: 1950
                self.log.debug(f"Batch of {len(test_batch)} is too big. Let's stick to {len(test_batch) - 1} then")
                break
            else:
                self.log.debug(f"Batch of {len(test_batch)} stakers fits in single TX ({estimated_gas} gas). "
                               f"Trying to squeeze one more staker...")
                last_good_batch = test_batch
                batch_size += 1

        if not last_good_batch:
            message = "It was not possible to find a new batch of deposits. "
            raise ValueError(message)

        batch_parameters = self.staking_agent.construct_batch_deposit_parameters(deposits=last_good_batch)
        receipt = self.staking_agent.batch_deposit(*batch_parameters,
                                                   sender_address=sender_address,
                                                   gas_limit=gas_limit)

        deposited_stakers = list(last_good_batch.keys())
        self.deposited.update(deposited_stakers)
        return deposited_stakers, receipt

    @property
    def pending_deposits(self) -> List[str]:
        pending_deposits = [staker for staker in self.allocations.keys() if staker not in self.deposited]
        return pending_deposits


class MultiSigActor(BaseActor):
    class UnknownExecutive(Exception):
        """
        Raised when Executive is not listed as a owner of the MultiSig.
        """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.multisig_agent = ContractAgency.get_agent(MultiSigAgent, registry=self.registry)


class Trustee(MultiSigActor):
    """
    A member of a MultiSigBoard given the power and
    obligation to execute an authorized transaction on
    behalf of the board of executives.
    """

    class NoAuthorizations(RuntimeError):
        """Raised when there are zero authorizations."""

    def __init__(self,
                 checksum_address: str,
                 client_password: str = None,
                 *args, **kwargs):
        super().__init__(checksum_address=checksum_address, *args, **kwargs)
        self.authorizations = dict()
        self.executive_addresses = tuple(
            self.multisig_agent.owners)  # TODO: Investigate unresolved reference to .owners (linter)
        if client_password:  # TODO: Consider an is_transacting parameter
            self.transacting_power = TransactingPower(password=client_password,
                                                      account=checksum_address)
            self.transacting_power.activate()

    def add_authorization(self, authorization, proposal: Proposal) -> str:
        executive_address = authorization.recover_executive_address(proposal)
        if executive_address not in self.executive_addresses:
            raise self.UnknownExecutive(f"Executive {executive_address} is not listed as an owner of the MultiSig.")
        if executive_address in self.authorizations:
            raise ValueError(f"There is already an authorization from executive {executive_address}")

        self.authorizations[executive_address] = authorization
        return executive_address

    def _combine_authorizations(self) -> Tuple[List[bytes], ...]:
        if not self.authorizations:
            raise self.NoAuthorizations

        all_v, all_r, all_s = list(), list(), list()

        def order_by_address(executive_address_to_sort):
            """
            Authorizations (i.e., signatures) must be provided to the MultiSig in increasing order by signing address
            """
            return Web3.toInt(to_canonical_address(executive_address_to_sort))

        for executive_address in sorted(self.authorizations.keys(), key=order_by_address):
            authorization = self.authorizations[executive_address]
            r, s, v = authorization.components
            all_v.append(Web3.toInt(v))  # v values are passed to the contract as ints, not as bytes
            all_r.append(r)
            all_s.append(s)

        return all_r, all_s, all_v

    def execute(self, proposal: Proposal) -> dict:

        if proposal.trustee_address != self.checksum_address:
            raise ValueError(f"This proposal is meant to be executed by trustee {proposal.trustee_address}, "
                             f"not by this trustee ({self.checksum_address})")
        # TODO: check for inconsistencies (nonce, etc.)

        r, s, v = self._combine_authorizations()
        receipt = self.multisig_agent.execute(sender_address=self.checksum_address,
                                              # TODO: Investigate unresolved reference to .execute
                                              v=v, r=r, s=s,
                                              destination=proposal.target_address,
                                              value=proposal.value,
                                              data=proposal.data)
        return receipt

    def create_transaction_proposal(self, transaction):
        proposal = Proposal.from_transaction(transaction,
                                             multisig_agent=self.multisig_agent,
                                             trustee_address=self.checksum_address)
        return proposal

    # MultiSig management proposals

    def propose_adding_owner(self, new_owner_address: str, evidence: str) -> Proposal:
        # TODO: Use evidence to ascertain new owner can transact with this address
        tx = self.multisig_agent.build_add_owner_tx(new_owner_address=new_owner_address)
        proposal = self.create_transaction_proposal(tx)
        return proposal

    def propose_removing_owner(self, owner_address: str) -> Proposal:
        tx = self.multisig_agent.build_remove_owner_tx(owner_address=owner_address)
        proposal = self.create_transaction_proposal(tx)
        return proposal

    def propose_changing_threshold(self, new_threshold: int) -> Proposal:
        tx = self.multisig_agent.build_change_threshold_tx(new_threshold)
        proposal = self.create_transaction_proposal(tx)
        return proposal


class Executive(MultiSigActor):
    """
    An actor having the power to authorize transaction executions to a delegated trustee.
    """

    def __init__(self,
                 checksum_address: str,
                 signer: Signer = None,
                 client_password: str = None,
                 *args, **kwargs):
        super().__init__(checksum_address=checksum_address, *args, **kwargs)

        if checksum_address not in self.multisig_agent.owners:
            raise self.UnknownExecutive(f"Executive {checksum_address} is not listed as an owner of the MultiSig. "
                                        f"Current owners are {self.multisig_agent.owners}")
        self.signer = signer
        if signer:
            self.transacting_power = TransactingPower(signer=signer,
                                                      password=client_password,
                                                      account=checksum_address)
            self.transacting_power.activate()

    def authorize_proposal(self, proposal) -> Authorization:
        # TODO: Double-check that the digest corresponds to the real data to sign
        signature = self.signer.sign_data_for_validator(account=self.checksum_address,
                                                        message=proposal.application_specific_data,
                                                        validator_address=self.multisig_agent.contract_address)
        authorization = Authorization.deserialize(data=Web3.toBytes(hexstr=signature))
        return authorization


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
                 individual_allocation: IndividualAllocationRegistry = None,
                 *args, **kwargs) -> None:

        super().__init__(*args, **kwargs)
        self.log = Logger("staker")

        self.is_me = is_me
        self.__worker_address = None

        # Blockchain
        self.policy_agent = ContractAgency.get_agent(PolicyManagerAgent, registry=self.registry)
        self.staking_agent = ContractAgency.get_agent(StakingEscrowAgent, registry=self.registry)
        self.economics = EconomicsFactory.get_economics(registry=self.registry)

        # Staking via contract
        self.individual_allocation = individual_allocation
        if self.individual_allocation:
            self.beneficiary_address = individual_allocation.beneficiary_address
            self.checksum_address = individual_allocation.contract_address
            self.preallocation_escrow_agent = PreallocationEscrowAgent(registry=self.registry,
                                                                       allocation_registry=self.individual_allocation,
                                                                       beneficiary=self.beneficiary_address)
        else:
            self.beneficiary_address = None
            self.preallocation_escrow_agent = None

        # Check stakes
        self.stakes = StakeList(registry=self.registry, checksum_address=self.checksum_address)

    def refresh_stakes(self):
        self.stakes.refresh()

    @property
    def is_contract(self) -> bool:
        return self.preallocation_escrow_agent is not None

    def to_dict(self) -> dict:
        stake_info = [stake.to_stake_info() for stake in self.stakes]
        worker_address = self.worker_address or NULL_ADDRESS
        staker_funds = {'ETH': int(self.eth_balance), 'NU': int(self.token_balance)}
        staker_payload = {'staker': self.checksum_address,
                          'balances': staker_funds,
                          'worker': worker_address,
                          'stakes': stake_info}
        return staker_payload

    @property
    def is_staking(self) -> bool:
        """Checks if this Staker currently has active stakes / locked tokens."""
        return bool(self.stakes)

    def owned_tokens(self) -> NU:
        """
        Returns all tokens that belong to the staker, including locked, unlocked and rewards.
        """
        raw_value = self.staking_agent.owned_tokens(staker_address=self.checksum_address)
        value = NU.from_nunits(raw_value)
        return value

    def locked_tokens(self, periods: int = 0) -> NU:
        """Returns the amount of tokens this staker has locked for a given duration in periods."""
        raw_value = self.staking_agent.get_locked_tokens(staker_address=self.checksum_address, periods=periods)
        value = NU.from_nunits(raw_value)
        return value

    @property
    def current_stake(self) -> NU:
        """The total number of staked tokens, i.e., tokens locked in the current period."""
        return self.locked_tokens(periods=0)

    def stakes_filtered_by_status(self, parent_status: Stake.Status) -> Iterable[Stake]:
        """Returns stakes for this staker which have specified or child status."""

        # Read once from chain and reuse these values
        staker_info = self.staking_agent.get_staker_info(self.checksum_address)  # TODO related to #1514
        current_period = self.staking_agent.get_current_period()                 # TODO #1514 this is online only.

        stakes = (stake for stake in self.stakes if stake.status(staker_info, current_period).is_child(parent_status))
        return stakes

    def sorted_stakes(self, parent_status: Stake.Status = None) -> List[Stake]:
        """Returns a list of filtered stakes sorted by account wallet index."""
        filtered_stakes = self.stakes_filtered_by_status(parent_status) if parent_status is not None else self.stakes
        stakes = sorted(filtered_stakes, key=lambda s: s.address_index_ordering_key)
        return stakes

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
            additional_periods = datetime_to_period(datetime=expiration,
                                                    seconds_per_period=self.economics.seconds_per_period) - current_stake.final_locked_period
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
                         amount: NU = None,
                         lock_periods: int = None,
                         expiration: maya.MayaDT = None,
                         entire_balance: bool = False
                         ) -> TxReceipt:

        """Create a new stake."""

        # Duration
        if not (bool(lock_periods) ^ bool(expiration)):
            raise ValueError(f"Pass either lock periods or expiration; got {'both' if lock_periods else 'neither'}")
        if expiration:
            lock_periods = calculate_period_duration(future_time=expiration,
                                                     seconds_per_period=self.economics.seconds_per_period)

        # Value
        if entire_balance and amount:
            raise ValueError("Specify an amount or entire balance, not both")
        elif not entire_balance and not amount:
            raise ValueError("Specify an amount or entire balance, got neither")

        token_balance = self.token_balance
        if entire_balance:
            amount = token_balance
        if not token_balance >= amount:
            raise self.InsufficientTokens(f"Insufficient token balance ({token_balance}) "
                                          f"for new stake initialization of {amount}")

        # Write to blockchain
        new_stake = Stake.initialize_stake(staking_agent=self.staking_agent,
                                           economics=self.economics,
                                           checksum_address=self.checksum_address,
                                           amount=amount,
                                           lock_periods=lock_periods)

        # Create stake on-chain
        receipt = self._deposit(amount=new_stake.value.to_nunits(), lock_periods=new_stake.duration)

        # Log and return receipt
        self.log.info(f"{self.checksum_address} initialized new stake: {amount} tokens for {lock_periods} periods")

        # Update staking cache element
        self.refresh_stakes()

        return receipt

    def _ensure_stake_exists(self, stake: Stake):
        if len(self.stakes) <= stake.index:
            raise ValueError(f"There is no stake with index {stake.index}")
        if self.stakes[stake.index] != stake:
            raise ValueError(f"Stake with index {stake.index} is not equal to provided stake")

    @only_me
    def divide_stake(self,
                     stake: Stake,
                     target_value: NU,
                     additional_periods: int = None,
                     expiration: maya.MayaDT = None
                     ) -> TxReceipt:
        self._ensure_stake_exists(stake)

        if not (bool(additional_periods) ^ bool(expiration)):
            raise ValueError(f"Pass either the number of lock periods or expiration; "
                             f"got {'both' if additional_periods else 'neither'}")

        # Calculate stake duration in periods
        if expiration:
            additional_periods = datetime_to_period(datetime=expiration, seconds_per_period=self.economics.seconds_per_period) - stake.final_locked_period
            if additional_periods <= 0:
                raise ValueError(f"New expiration {expiration} must be at least 1 period from the "
                                 f"current stake's end period ({stake.final_locked_period}).")

        # Read on-chain stake and validate
        stake.sync()
        validate_divide(stake=stake, target_value=target_value, additional_periods=additional_periods)

        # Do it already!
        receipt = self._divide_stake(stake_index=stake.index,
                                     additional_periods=additional_periods,
                                     target_value=int(target_value))

        # Update staking cache element
        self.refresh_stakes()

        return receipt

    @only_me
    def increase_stake(self,
                       stake: Stake,
                       amount: NU = None,
                       entire_balance: bool = False
                       ) -> TxReceipt:
        """Add tokens to existing stake."""
        self._ensure_stake_exists(stake)

        # Value
        if not (bool(entire_balance) ^ bool(amount)):
            raise ValueError(f"Pass either an amount or entire balance; "
                             f"got {'both' if entire_balance else 'neither'}")

        token_balance = self.token_balance
        if entire_balance:
            amount = token_balance
        if not token_balance >= amount:
            raise self.InsufficientTokens(f"Insufficient token balance ({token_balance}) "
                                          f"to increase stake by {amount}")

        # Read on-chain stake and validate
        stake.sync()
        validate_increase(stake=stake, amount=amount)

        # Write to blockchain
        receipt = self._deposit_and_increase(stake_index=stake.index, amount=int(amount))

        # Update staking cache element
        self.refresh_stakes()
        return receipt

    @only_me
    def prolong_stake(self,
                      stake: Stake,
                      additional_periods: int = None,
                      expiration: maya.MayaDT = None) -> TxReceipt:
        self._ensure_stake_exists(stake)

        if not (bool(additional_periods) ^ bool(expiration)):
            raise ValueError(f"Pass either the number of lock periods or expiration; "
                             f"got {'both' if additional_periods else 'neither'}")

        # Calculate stake duration in periods
        if expiration:
            additional_periods = datetime_to_period(datetime=expiration,
                                                    seconds_per_period=self.economics.seconds_per_period) - stake.final_locked_period
            if additional_periods <= 0:
                raise ValueError(f"New expiration {expiration} must be at least 1 period from the "
                                 f"current stake's end period ({stake.final_locked_period}).")

        # Read on-chain stake and validate
        stake.sync()
        validate_prolong(stake=stake, additional_periods=additional_periods)

        receipt = self._prolong_stake(stake_index=stake.index, lock_periods=additional_periods)

        # Update staking cache element
        self.refresh_stakes()
        return receipt

    def _prolong_stake(self, stake_index: int, lock_periods: int) -> TxReceipt:
        """Public facing method for stake prolongation."""
        # TODO #1497 #1358
        # if self.is_contract:
        #     receipt = self.preallocation_escrow_agent.prolong_stake(stake_index=stake_index, lock_periods=lock_periods)
        # else:
        receipt = self.staking_agent.prolong_stake(stake_index=stake_index,
                                                   periods=lock_periods,
                                                   staker_address=self.checksum_address)
        return receipt

    def _deposit(self, amount: int, lock_periods: int) -> TxReceipt:
        """Public facing method for token locking."""
        if self.is_contract:
            receipt = self.preallocation_escrow_agent.deposit_as_staker(amount=amount, lock_periods=lock_periods)
        else:
            receipt = self.token_agent.approve_and_call(amount=amount,
                                                        target_address=self.staking_agent.contract_address,
                                                        sender_address=self.checksum_address,
                                                        call_data=Web3.toBytes(lock_periods))
        return receipt

    def _divide_stake(self, stake_index: int, additional_periods: int, target_value: int) -> TxReceipt:
        """Public facing method for stake dividing."""
        # TODO #1497 #1358
        # if self.is_contract:
        #     receipt = self.preallocation_escrow_agent...
        # else:
        receipt = self.staking_agent.divide_stake(staker_address=self.checksum_address,
                                                  stake_index=stake_index,
                                                  target_value=target_value,
                                                  periods=additional_periods)
        return receipt

    def _deposit_and_increase(self, stake_index: int, amount: int) -> TxReceipt:
        """Public facing method for deposit and increasing stake."""
        # TODO #1497 #1358
        # if self.is_contract:
        #     receipt = self.preallocation_escrow_agent...
        # else:
        self.token_agent.increase_allowance(increase=amount,
                                            sender_address=self.checksum_address,
                                            spender_address=self.staking_agent.contract.address)
        receipt = self.staking_agent.deposit_and_increase(staker_address=self.checksum_address,
                                                          stake_index=stake_index,
                                                          amount=amount)
        return receipt

    @property
    def is_restaking(self) -> bool:
        restaking = self.staking_agent.is_restaking(staker_address=self.checksum_address)
        return restaking

    @only_me
    @save_receipt
    def _set_restaking(self, value: bool) -> TxReceipt:
        if self.is_contract:
            receipt = self.preallocation_escrow_agent.set_restaking(value=value)
        else:
            receipt = self.staking_agent.set_restaking(staker_address=self.checksum_address, value=value)
        return receipt

    def enable_restaking(self) -> TxReceipt:
        receipt = self._set_restaking(value=True)
        return receipt

    @only_me
    @save_receipt
    def enable_restaking_lock(self, release_period: int) -> TxReceipt:
        current_period = self.staking_agent.get_current_period()
        if release_period < current_period:
            raise ValueError(f"Release period for re-staking lock must be in the future.  "
                             f"Current period is {current_period}, got '{release_period}'.")
        if self.is_contract:
            receipt = self.preallocation_escrow_agent.lock_restaking(release_period=release_period)
        else:
            receipt = self.staking_agent.lock_restaking(staker_address=self.checksum_address,
                                                        release_period=release_period)
        return receipt

    @property
    def restaking_lock_enabled(self) -> bool:
        status = self.staking_agent.is_restaking_locked(staker_address=self.checksum_address)
        return status

    def disable_restaking(self) -> TxReceipt:
        receipt = self._set_restaking(value=False)
        return receipt

    @property
    def is_winding_down(self) -> bool:
        winding_down = self.staking_agent.is_winding_down(staker_address=self.checksum_address)
        return winding_down

    @only_me
    @save_receipt
    def _set_winding_down(self, value: bool) -> TxReceipt:
        if self.is_contract:
            receipt = self.preallocation_escrow_agent.set_winding_down(value=value)
        else:
            receipt = self.staking_agent.set_winding_down(staker_address=self.checksum_address, value=value)
        return receipt

    def enable_winding_down(self) -> TxReceipt:
        receipt = self._set_winding_down(value=True)
        return receipt

    def disable_winding_down(self) -> TxReceipt:
        receipt = self._set_winding_down(value=False)
        return receipt

    def non_withdrawable_stake(self) -> NU:
        staked_amount: NuNits = self.staking_agent.non_withdrawable_stake(staker_address=self.checksum_address)
        return NU.from_nunits(staked_amount)

    def mintable_periods(self) -> int:
        """
        Returns number of periods that can be rewarded in the current period. Value in range [0, 2]
        """
        current_period: Period = self.staking_agent.get_current_period()
        previous_period: int = current_period - 1
        current_committed_period: Period = self.staking_agent.get_current_committed_period(staker_address=self.checksum_address)
        next_committed_period: Period = self.staking_agent.get_next_committed_period(staker_address=self.checksum_address)

        mintable_periods: int = 0
        if 0 < current_committed_period <= previous_period:
            mintable_periods += 1
        if 0 < next_committed_period <= previous_period:
            mintable_periods += 1

        return mintable_periods

    #
    # Bonding with Worker
    #
    @only_me
    @save_receipt
    @validate_checksum_address
    def bond_worker(self, worker_address: str) -> TxReceipt:
        if self.is_contract:
            receipt = self.preallocation_escrow_agent.bond_worker(worker_address=worker_address)
        else:
            receipt = self.staking_agent.bond_worker(staker_address=self.checksum_address,
                                                     worker_address=worker_address)
        self.__worker_address = worker_address
        return receipt

    @property
    def worker_address(self) -> str:
        if self.__worker_address:
            # TODO: This is broken for StakeHolder with different stakers - See #1358
            return self.__worker_address
        else:
            worker_address = self.staking_agent.get_worker_from_staker(staker_address=self.checksum_address)
            self.__worker_address = worker_address

        if self.__worker_address == NULL_ADDRESS:
            return NO_WORKER_BONDED.bool_value(False)
        return self.__worker_address

    @only_me
    @save_receipt
    def unbond_worker(self) -> TxReceipt:
        if self.is_contract:
            receipt = self.preallocation_escrow_agent.release_worker()
        else:
            receipt = self.staking_agent.release_worker(staker_address=self.checksum_address)
        self.__worker_address = NULL_ADDRESS
        return receipt

    #
    # Reward and Collection
    #

    @only_me
    @save_receipt
    def mint(self) -> TxReceipt:
        """Computes and transfers tokens to the staker's account"""
        if self.is_contract:
            receipt = self.preallocation_escrow_agent.mint()
        else:
            receipt = self.staking_agent.mint(staker_address=self.checksum_address)
        return receipt

    def calculate_staking_reward(self) -> int:
        staking_reward = self.staking_agent.calculate_staking_reward(staker_address=self.checksum_address)
        return staking_reward

    def calculate_policy_fee(self) -> int:
        policy_fee = self.policy_agent.get_fee_amount(staker_address=self.checksum_address)
        return policy_fee

    @only_me
    @save_receipt
    @validate_checksum_address
    def collect_policy_fee(self, collector_address=None) -> TxReceipt:
        """Collect fees (ETH) earned since last withdrawal"""
        if self.is_contract:
            if collector_address and collector_address != self.beneficiary_address:
                raise ValueError("Policy fees must be withdrawn to the beneficiary address")
            self.preallocation_escrow_agent.collect_policy_fee()  # TODO save receipt
            receipt = self.preallocation_escrow_agent.withdraw_eth()
        else:
            withdraw_address = collector_address or self.checksum_address
            receipt = self.policy_agent.collect_policy_fee(collector_address=withdraw_address,
                                                           staker_address=self.checksum_address)
        return receipt

    @only_me
    @save_receipt
    def collect_staking_reward(self) -> TxReceipt:
        """Withdraw tokens rewarded for staking"""
        if self.is_contract:
            reward_amount = self.calculate_staking_reward()
            self.log.debug(f"Withdrawing staking reward ({NU.from_nunits(reward_amount)}) to {self.checksum_address}")
            receipt = self.preallocation_escrow_agent.withdraw_as_staker(value=reward_amount)
        else:
            receipt = self.staking_agent.collect_staking_reward(staker_address=self.checksum_address)
        return receipt

    @only_me
    @save_receipt
    def withdraw(self, amount: NU) -> TxReceipt:
        """Withdraw tokens from StakingEscrow (assuming they're unlocked)"""
        if self.is_contract:
            receipt = self.preallocation_escrow_agent.withdraw_as_staker(value=int(amount))
        else:
            receipt = self.staking_agent.withdraw(staker_address=self.checksum_address,
                                                  amount=int(amount))
        return receipt

    @only_me
    @save_receipt
    def withdraw_preallocation_tokens(self, amount: NU) -> TxReceipt:
        """Withdraw tokens from PreallocationEscrow (assuming they're unlocked)"""
        if amount <= 0:
            raise ValueError(f"Don't try to withdraw {amount}.")
        if self.is_contract:
            receipt = self.preallocation_escrow_agent.withdraw_tokens(value=int(amount))
        else:
            raise TypeError("This method can only be used when staking via a contract")
        return receipt

    @only_me
    @save_receipt
    def withdraw_preallocation_eth(self) -> TxReceipt:
        """Withdraw ETH from PreallocationEscrow"""
        if self.is_contract:
            receipt = self.preallocation_escrow_agent.withdraw_eth()
        else:
            raise TypeError("This method can only be used when staking via a contract")
        return receipt

    @property
    def missing_commitments(self) -> int:
        staker_address = self.checksum_address
        missing = self.staking_agent.get_missing_commitments(checksum_address=staker_address)
        return missing

    @only_me
    @save_receipt
    def set_min_fee_rate(self, min_rate: int) -> TxReceipt:
        """Public facing method for staker to set the minimum acceptable fee rate for their associated worker"""
        minimum, _default, maximum = self.policy_agent.get_fee_rate_range()
        if min_rate < minimum or min_rate > maximum:
            raise ValueError(f"Minimum fee rate {min_rate} must fall within global fee range of [{minimum}, {maximum}]")
        if self.is_contract:
            receipt = self.preallocation_escrow_agent.set_min_fee_rate(min_rate=min_rate)
        else:
            receipt = self.policy_agent.set_min_fee_rate(staker_address=self.checksum_address, min_rate=min_rate)
        return receipt

    @property
    def min_fee_rate(self) -> int:
        """Minimum fee rate that staker accepts"""
        staker_address = self.checksum_address
        min_fee = self.policy_agent.get_min_fee_rate(staker_address)
        return min_fee

    @property
    def raw_min_fee_rate(self) -> int:
        """Minimum acceptable fee rate set by staker for their associated worker.
        This fee rate is only used if it falls within the global fee range.
        If it doesn't a default fee rate is used instead of the raw value (see `min_fee_rate`)"""
        staker_address = self.checksum_address
        min_fee = self.policy_agent.get_raw_min_fee_rate(staker_address)
        return min_fee


class Worker(NucypherTokenActor):
    """
    Ursula baseclass for blockchain operations, practically carrying a pickaxe.
    """

    BONDING_TIMEOUT = None  # (None or 0) == indefinite
    BONDING_POLL_RATE = 10

    class WorkerError(NucypherTokenActor.ActorError):
        pass

    class UnbondedWorker(WorkerError):
        """Raised when the Worker is not bonded to a Staker in the StakingEscrow contract."""
        crash_right_now = True

    def __init__(self,
                 is_me: bool,
                 work_tracker: WorkTracker = None,
                 worker_address: str = None,
                 start_working_now: bool = True,
                 block_until_ready: bool = True,
                 *args, **kwargs):

        super().__init__(*args, **kwargs)
        self.log = Logger("worker")

        self.is_me = is_me

        # self._checksum_address = None  # Stake Address  # TODO - wait, why?  Why are we setting this to None when it may have already been set in an outer method?
        self.__worker_address = worker_address

        # Agency
        self.staking_agent = ContractAgency.get_agent(StakingEscrowAgent,
                                                      registry=self.registry)  # type: StakingEscrowAgent

        # Someday, when we have Workers for tasks other than PRE, this might instead be composed on Ursula.
        self.policy_agent = ContractAgency.get_agent(PolicyManagerAgent,
                                                     registry=self.registry)  # type: PolicyManagerAgent

        # Stakes
        self.__start_time = WORKER_NOT_RUNNING
        self.__uptime_period = WORKER_NOT_RUNNING

        # Workers cannot be started without being assigned a stake first.
        if is_me:
            if block_until_ready:
                self.block_until_ready()

            if start_working_now:
                self.stakes = StakeList(registry=self.registry, checksum_address=self.checksum_address)
                self.stakes.refresh()
                self.work_tracker = work_tracker or WorkTracker(worker=self)
                self.work_tracker.start(act_now=start_working_now)

    def block_until_ready(self, poll_rate: int = None, timeout: int = None):
        """
        Polls the staking_agent and blocks until the staking address is not
        a null address for the given worker_address. Once the worker is bonded, it returns the staker address.
        """
        if not self.__worker_address:
            raise RuntimeError("No worker address available")

        timeout = timeout or self.BONDING_TIMEOUT
        poll_rate = poll_rate or self.BONDING_POLL_RATE
        staking_agent = ContractAgency.get_agent(StakingEscrowAgent, registry=self.registry)  # TODO: use the agent on self
        client = staking_agent.blockchain.client
        start = maya.now()

        emitter = StdoutEmitter()  # TODO: Make injectable, or embed this logic into Ursula
        emitter.message("Waiting for bonding and funding...", color='yellow')

        funded, bonded = False, False
        while True:

            # Read
            staking_address = staking_agent.get_staker_from_worker(self.__worker_address)
            ether_balance = client.get_balance(self.__worker_address)

            # Bonding
            if (not bonded) and (staking_address != NULL_ADDRESS):
                bonded = True
                emitter.message(f"Worker is bonded to ({staking_address})!", color='green', bold=True)

            # Balance
            if ether_balance and (not funded):
                funded, balance = True, Web3.fromWei(ether_balance, 'ether')
                emitter.message(f"Worker is funded with {balance} ETH!", color='green', bold=True)

            # Success and Escape
            if staking_address != NULL_ADDRESS and ether_balance:
                self._checksum_address = staking_address

                # TODO: #1823 - Workaround for new nickname every restart
                self.nickname, self.nickname_metadata = nickname_from_seed(self.checksum_address)
                break

            # Crash on Timeout
            if timeout:
                now = maya.now()
                delta = now - start
                if delta.total_seconds() >= timeout:
                    if staking_address == NULL_ADDRESS:
                        raise self.UnbondedWorker(
                            f"Worker {self.__worker_address} not bonded after waiting {timeout} seconds.")
                    elif not ether_balance:
                        raise RuntimeError(
                            f"Worker {self.__worker_address} has no ether after waiting {timeout} seconds.")

            # Increment
            time.sleep(poll_rate)

    @property
    def eth_balance(self) -> Decimal:
        """Return this workers's current ETH balance"""
        blockchain = BlockchainInterfaceFactory.get_interface()  # TODO: EthAgent?  #1509
        balance = blockchain.client.get_balance(self.__worker_address)
        return blockchain.client.w3.fromWei(balance, 'ether')

    @property
    def token_balance(self) -> NU:
        """
        Return this worker's current token balance.
        Note: Workers typically do not control any tokens.
        """
        balance = int(self.token_agent.get_balance(address=self.__worker_address))
        nu_balance = NU(balance, 'NuNit')
        return nu_balance

    @property
    def last_committed_period(self) -> int:
        period = self.staking_agent.get_last_committed_period(staker_address=self.checksum_address)
        return period

    @only_me
    @save_receipt
    def commit_to_next_period(self) -> TxReceipt:
        """For each period that the worker makes a commitment, the staker is rewarded"""
        receipt = self.staking_agent.commit_to_next_period(worker_address=self.__worker_address)
        return receipt

    @property
    def missing_commitments(self) -> int:
        staker_address = self.checksum_address
        missing = self.staking_agent.get_missing_commitments(checksum_address=staker_address)
        return missing


class BlockchainPolicyAuthor(NucypherTokenActor):
    """Alice base class for blockchain operations, mocking up new policies!"""

    def __init__(self,
                 checksum_address: str,
                 rate: int = None,
                 duration_periods: int = None,
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

        self.economics = EconomicsFactory.get_economics(registry=self.registry)
        self.rate = rate
        self.duration_periods = duration_periods

    @property
    def default_rate(self):
        _minimum, default, _maximum = self.policy_agent.get_fee_rate_range()
        return default

    def generate_policy_parameters(self,
                                   number_of_ursulas: int = None,
                                   duration_periods: int = None,
                                   expiration: maya.MayaDT = None,
                                   value: int = None,
                                   rate: int = None,
                                   ) -> dict:
        """
        Construct policy creation from parameters or overrides.
        """

        if not duration_periods and not expiration:
            raise ValueError("Policy end time must be specified as 'expiration' or 'duration_periods', got neither.")

        # Merge injected and default params.
        rate = rate or self.rate  # TODO conflict with CLI default value, see #1709
        duration_periods = duration_periods or self.duration_periods

        # Calculate duration in periods and expiration datetime
        if duration_periods:
            # Duration equals one period means that expiration date is the last second of the current period
            expiration = datetime_at_period(self.staking_agent.get_current_period() + duration_periods,
                                            seconds_per_period=self.economics.seconds_per_period,
                                            start_of_period=True)
            expiration -= 1  # Get the last second of the target period
        else:
            now = self.staking_agent.blockchain.get_blocktime()
            duration_periods = calculate_period_duration(now=maya.MayaDT(now),
                                                         future_time=expiration,
                                                         seconds_per_period=self.economics.seconds_per_period)
            duration_periods += 1  # Number of all included periods

        from nucypher.policy.policies import BlockchainPolicy
        blockchain_payload = BlockchainPolicy.generate_policy_parameters(n=number_of_ursulas,
                                                                         duration_periods=duration_periods,
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

    def __init__(self, checksum_address: str, *args, **kwargs):
        super().__init__(checksum_address=checksum_address, *args, **kwargs)
        self.adjudicator_agent = ContractAgency.get_agent(AdjudicatorAgent, registry=self.registry)

    @save_receipt
    def request_evaluation(self, evidence) -> dict:
        receipt = self.adjudicator_agent.evaluate_cfrag(evidence=evidence, sender_address=self.checksum_address)
        return receipt

    def was_this_evidence_evaluated(self, evidence) -> dict:
        receipt = self.adjudicator_agent.was_this_evidence_evaluated(evidence=evidence)
        return receipt


class Wallet:
    """
    Account management abstraction on top of blockchain providers and external signers
    """

    class UnknownAccount(KeyError):
        pass

    def __init__(self,
                 client_addresses: set = None,
                 provider_uri: str = None,
                 signer=None):

        self.__client_accounts = list()
        self.__transacting_powers = dict()

        # Blockchain
        self.blockchain = BlockchainInterfaceFactory.get_interface(provider_uri)
        self.__signer = signer

        self.__get_accounts()
        if client_addresses:
            self.__client_accounts.extend([a for a in client_addresses if a not in self.__client_accounts])

    @validate_checksum_address
    def __contains__(self, checksum_address: str) -> bool:
        return bool(checksum_address in self.accounts)

    @property
    def active_account(self) -> str:
        return self.blockchain.transacting_power.account

    def __get_accounts(self) -> None:
        if self.__signer:
            signer_accounts = self.__signer.accounts
            self.__client_accounts.extend([a for a in signer_accounts if a not in self.__client_accounts])
        client_accounts = self.blockchain.client.accounts  # Accounts via connected provider
        self.__client_accounts.extend([a for a in client_accounts if a not in self.__client_accounts])

    @property
    def accounts(self) -> Tuple:
        return tuple(self.__client_accounts)

    @validate_checksum_address
    def activate_account(self,
                         checksum_address: str,
                         signer: Optional[Signer] = None,
                         password: Optional[str] = None
                         ) -> None:

        if checksum_address not in self:
            self.__signer = signer or Web3Signer(client=self.blockchain.client)
            if isinstance(self.__signer, KeystoreSigner):
                raise BaseActor.ActorError(f"Staking operations are not permitted while using a local keystore signer.")
            self.__get_accounts()
            if checksum_address not in self:
                raise self.UnknownAccount
        try:
            transacting_power = self.__transacting_powers[checksum_address]
        except KeyError:
            transacting_power = TransactingPower(signer=self.__signer or Web3Signer(client=self.blockchain.client),
                                                 password=password,
                                                 account=checksum_address)
            self.__transacting_powers[checksum_address] = transacting_power
        transacting_power.activate(password=password)

    def eth_balance(self, account: str) -> int:
        return self.blockchain.client.get_balance(account)

    def token_balance(self, account: str, registry: BaseContractRegistry) -> int:
        token_agent = ContractAgency.get_agent(NucypherTokenAgent, registry)  # type: NucypherTokenAgent
        return token_agent.get_balance(account)


class StakeHolder(Staker):
    banner = STAKEHOLDER_BANNER

    #
    # StakeHolder
    #
    def __init__(self,
                 is_me: bool = True,
                 initial_address: str = None,
                 checksum_addresses: set = None,
                 signer: Signer = None,
                 *args, **kwargs):

        self.staking_interface_agent = None

        super().__init__(is_me=is_me, *args, **kwargs)
        self.log = Logger(f"stakeholder")

        # Wallet
        self.wallet = Wallet(client_addresses=checksum_addresses, signer=signer)
        if initial_address:
            # If an initial address was passed,
            # it is safe to understand that it has already been used at a higher level.
            if initial_address not in self.wallet:
                message = f"Account {initial_address} is not known by this Ethereum client. Is it a HW account? " \
                          f"If so, make sure that your device is plugged in and you use the --hw-wallet flag."
                raise Wallet.UnknownAccount(message)
            self.set_staker(checksum_address=initial_address)

    @validate_checksum_address
    def set_staker(self, checksum_address: str) -> None:

        # Check if staker is already set
        if self.checksum_address == checksum_address:
            return

        if self.is_contract:
            original_form = f"{self.beneficiary_address[0:8]} (contract {self.checksum_address[0:8]})"
        else:
            original_form = self.checksum_address

        # This handles both regular staking and staking via a contract
        if self.individual_allocation:
            if checksum_address != self.individual_allocation.beneficiary_address:
                raise ValueError(f"Beneficiary {self.individual_allocation.beneficiary_address} in individual "
                                 f"allocations does not match this checksum address ({checksum_address})")
            staking_address = self.individual_allocation.contract_address
            self.beneficiary_address = self.individual_allocation.beneficiary_address
            self.preallocation_escrow_agent = PreallocationEscrowAgent(registry=self.registry,
                                                                       allocation_registry=self.individual_allocation,
                                                                       beneficiary=self.beneficiary_address)
        else:
            staking_address = checksum_address
            self.beneficiary_address = None
            self.preallocation_escrow_agent = None

        self.checksum_address = staking_address
        self.stakes = StakeList(registry=self.registry, checksum_address=staking_address)
        self.refresh_stakes()

        if self.is_contract:
            new_form = f"{self.beneficiary_address[0:8]} (contract {self.checksum_address[0:8]})"
        else:
            new_form = self.checksum_address

        self.log.info(f"Setting Staker from {original_form} to {new_form}.")

    @validate_checksum_address
    def assimilate(self, checksum_address: str = None, password: str = None) -> None:
        if checksum_address:
            self.set_staker(checksum_address=checksum_address)

        account = self.checksum_address if not self.individual_allocation else self.beneficiary_address
        self.wallet.activate_account(checksum_address=account, password=password)

    @validate_checksum_address
    def get_staker(self, checksum_address: str):
        if checksum_address not in self.wallet.accounts:
            raise ValueError(f"{checksum_address} is not a known client account.")
        staker = Staker(is_me=True, checksum_address=checksum_address, registry=self.registry)
        staker.refresh_stakes()
        return staker

    def get_stakers(self) -> List[Staker]:
        stakers = list()
        for account in self.wallet.accounts:
            staker = self.get_staker(checksum_address=account)
            stakers.append(staker)
        return stakers

    @property
    def total_stake(self) -> NU:
        """
        The total number of staked tokens, either locked or unlocked in the current period.
        """
        stake = sum(self.staking_agent.owned_tokens(staker_address=account) for account in self.wallet.accounts)
        nu_stake = NU.from_nunits(stake)
        return nu_stake


class Bidder(NucypherTokenActor):
    """WorkLock participant"""

    class BidderError(NucypherTokenActor.ActorError):
        pass

    class BiddingIsOpen(BidderError):
        pass

    class BiddingIsClosed(BidderError):
        pass

    class CancellationWindowIsOpen(BidderError):
        pass

    class CancellationWindowIsClosed(BidderError):
        pass

    class ClaimError(BidderError):
        pass

    class WhaleError(BidderError):
        pass

    @validate_checksum_address
    def __init__(self,
                 checksum_address: str,
                 transacting: bool = True,
                 signer: Signer = None,
                 client_password: str = None,
                 *args, **kwargs):

        super().__init__(checksum_address=checksum_address, *args, **kwargs)
        self.log = Logger(f"WorkLockBidder")
        self.worklock_agent = ContractAgency.get_agent(WorkLockAgent, registry=self.registry)  # type: WorkLockAgent
        self.staking_agent = ContractAgency.get_agent(StakingEscrowAgent, registry=self.registry)  # type: StakingEscrowAgent
        self.economics = EconomicsFactory.get_economics(registry=self.registry)

        if transacting:
            self.transacting_power = TransactingPower(signer=signer,
                                                      password=client_password,
                                                      account=checksum_address)
            self.transacting_power.activate()

        self._all_bonus_bidders = None

    def ensure_bidding_is_open(self, message: str = None) -> None:
        now = self.worklock_agent.blockchain.get_blocktime()
        start = self.worklock_agent.start_bidding_date
        end = self.worklock_agent.end_bidding_date
        if now < start:
            message = message or f'Bidding does not open until {maya.MayaDT(start).slang_date()}'
            raise self.BiddingIsClosed(message)
        if now >= end:
            message = message or f'Bidding closed at {maya.MayaDT(end).slang_date()}'
            raise self.BiddingIsClosed(message)

    def _ensure_bidding_is_closed(self, message: str = None) -> None:
        now = self.worklock_agent.blockchain.get_blocktime()
        end = self.worklock_agent.end_bidding_date
        if now < end:
            message = message or f"Bidding does not close until {maya.MayaDT(end).slang_date()}"
            raise self.BiddingIsOpen(message)

    def _ensure_cancellation_window(self, ensure_closed: bool = True, message: str = None) -> None:
        now = self.worklock_agent.blockchain.get_blocktime()
        end = self.worklock_agent.end_cancellation_date
        if ensure_closed and now < end:
            message = message or f"Operation cannot be performed while the cancellation window is still open " \
                                 f"(closes at {maya.MayaDT(end).slang_date()})."
            raise self.CancellationWindowIsOpen(message)
        elif not ensure_closed and now >= end:
            message = message or f"Operation is allowed only while the cancellation window is open " \
                                 f"(closed at {maya.MayaDT(end).slang_date()})."
            raise self.CancellationWindowIsClosed(message)

    #
    # Transactions
    #

    def place_bid(self, value: int) -> TxReceipt:
        self.ensure_bidding_is_open()
        minimum = self.worklock_agent.minimum_allowed_bid
        if not self.get_deposited_eth and value < minimum:
            raise self.BidderError(f"{prettify_eth_amount(value)} is too small a value for bidding; "
                                   f"bid must be at least {prettify_eth_amount(minimum)}")
        receipt = self.worklock_agent.bid(checksum_address=self.checksum_address, value=value)
        return receipt

    def claim(self) -> TxReceipt:

        # Require the cancellation window is closed
        self._ensure_cancellation_window(ensure_closed=True)

        if not self.worklock_agent.is_claiming_available():
            raise self.ClaimError(f"Claiming is not available yet")

        # Ensure the claim was not already placed
        if self.has_claimed:
            raise self.ClaimError(f"Bidder {self.checksum_address} already placed a claim.")

        # Require an active bid
        if not self.get_deposited_eth:
            raise self.ClaimError(f"No bids available for {self.checksum_address}")

        receipt = self.worklock_agent.claim(checksum_address=self.checksum_address)
        return receipt

    def cancel_bid(self) -> TxReceipt:
        self._ensure_cancellation_window(ensure_closed=False)

        # Require an active bid
        if not self.get_deposited_eth:
            self.BidderError(f"No bids available for {self.checksum_address}")

        receipt = self.worklock_agent.cancel_bid(checksum_address=self.checksum_address)
        return receipt

    def _get_max_bonus_bid_from_max_stake(self) -> int:
        """Returns maximum allowed bid calculated from maximum allowed locked tokens"""
        max_bonus_tokens = self.economics.maximum_allowed_locked - self.economics.minimum_allowed_locked
        bonus_eth_supply = sum(
            self._all_bonus_bidders.values()) if self._all_bonus_bidders else self.worklock_agent.get_bonus_eth_supply()
        bonus_worklock_supply = self.worklock_agent.get_bonus_lot_value()
        max_bonus_bid = max_bonus_tokens * bonus_eth_supply // bonus_worklock_supply
        return max_bonus_bid

    def get_whales(self, force_read: bool = False) -> Dict[str, int]:
        """Returns all worklock bidders over the whale threshold as a dictionary of addresses and bonus bid values."""
        max_bonus_bid_from_max_stake = self._get_max_bonus_bid_from_max_stake()

        bidders = dict()
        for bidder, bid in self._get_all_bonus_bidders(force_read).items():
            if bid > max_bonus_bid_from_max_stake:
                bidders[bidder] = bid
        return bidders

    def _get_all_bonus_bidders(self, force_read: bool = False) -> dict:
        if not force_read and self._all_bonus_bidders:
            return self._all_bonus_bidders

        bidders = self.worklock_agent.get_bidders()
        min_bid = self.economics.worklock_min_allowed_bid

        self._all_bonus_bidders = dict()
        for bidder in bidders:
            bid = self.worklock_agent.get_deposited_eth(bidder)
            if bid > min_bid:
                self._all_bonus_bidders[bidder] = bid - min_bid
        return self._all_bonus_bidders

    def _reduce_bids(self, whales: dict):

        min_whale_bonus_bid = min(whales.values())
        max_whale_bonus_bid = max(whales.values())

        # first step - align at a minimum bid
        if min_whale_bonus_bid != max_whale_bonus_bid:
            whales = dict.fromkeys(whales.keys(), min_whale_bonus_bid)
            self._all_bonus_bidders.update(whales)

        bonus_eth_supply = sum(self._all_bonus_bidders.values())
        bonus_worklock_supply = self.worklock_agent.get_bonus_lot_value()
        max_bonus_tokens = self.economics.maximum_allowed_locked - self.economics.minimum_allowed_locked
        if (min_whale_bonus_bid * bonus_worklock_supply) // bonus_eth_supply <= max_bonus_tokens:
            raise self.WhaleError(f"At least one of bidders {whales} has allowable bid")

        a = min_whale_bonus_bid * bonus_worklock_supply - max_bonus_tokens * bonus_eth_supply
        b = bonus_worklock_supply - max_bonus_tokens * len(whales)
        refund = -(-a // b)  # div ceil
        min_whale_bonus_bid -= refund
        whales = dict.fromkeys(whales.keys(), min_whale_bonus_bid)
        self._all_bonus_bidders.update(whales)

        return whales

    def force_refund(self) -> TxReceipt:
        self._ensure_cancellation_window(ensure_closed=True)

        whales = self.get_whales()
        if not whales:
            raise self.WhaleError(f"Force refund aborted: No whales detected and all bids qualify for claims.")

        new_whales = whales.copy()
        while new_whales:
            whales.update(new_whales)
            whales = self._reduce_bids(whales)
            new_whales = self.get_whales()

        receipt = self.worklock_agent.force_refund(checksum_address=self.checksum_address,
                                                   addresses=list(whales.keys()))

        if self.get_whales(force_read=True):
            raise RuntimeError(f"Internal error: offline simulation differs from transaction results")
        return receipt

    # TODO better control: max iterations, interactive mode
    def verify_bidding_correctness(self, gas_limit: int) -> dict:
        self._ensure_cancellation_window(ensure_closed=True)

        if self.worklock_agent.bidders_checked():
            raise self.BidderError(f"Check was already done")

        whales = self.get_whales()
        if whales:
            raise self.WhaleError(f"Some bidders have bids that are too high: {whales}")

        self.log.debug(f"Starting bidding verification. Next bidder to check: {self.worklock_agent.next_bidder_to_check()}")

        receipts = dict()
        iteration = 1
        while not self.worklock_agent.bidders_checked():
            self.transacting_power.activate()  # Refresh TransactingPower
            receipt = self.worklock_agent.verify_bidding_correctness(checksum_address=self.checksum_address,
                                                                     gas_limit=gas_limit)
            self.log.debug(f"Iteration {iteration}. Next bidder to check: {self.worklock_agent.next_bidder_to_check()}")
            receipts[iteration] = receipt
            iteration += 1
        return receipts

    def refund_deposit(self) -> dict:
        """Refund ethers for completed work"""
        if not self.available_refund:
            raise self.BidderError(f'There is no refund available for {self.checksum_address}')
        receipt = self.worklock_agent.refund(checksum_address=self.checksum_address)
        return receipt

    def withdraw_compensation(self) -> TxReceipt:
        """Withdraw compensation after force refund"""
        if not self.available_compensation:
            raise self.BidderError(f'There is no compensation available for {self.checksum_address}; '
                                   f'Did you mean to call "refund"?')
        receipt = self.worklock_agent.withdraw_compensation(checksum_address=self.checksum_address)
        return receipt

    #
    # Calls
    #

    @property
    def get_deposited_eth(self) -> int:
        bid = self.worklock_agent.get_deposited_eth(checksum_address=self.checksum_address)
        return bid

    @property
    def has_claimed(self) -> bool:
        has_claimed = self.worklock_agent.check_claim(self.checksum_address)
        return has_claimed

    @property
    def completed_work(self) -> int:
        work = self.staking_agent.get_completed_work(bidder_address=self.checksum_address)
        completed_work = work - self.refunded_work
        return completed_work

    @property
    def remaining_work(self) -> int:
        try:
            work = self.worklock_agent.get_remaining_work(checksum_address=self.checksum_address)
        except (TestTransactionFailed, ValidationError, ValueError):  # TODO: 1950
            work = 0
        return work

    @property
    def refunded_work(self) -> int:
        work = self.worklock_agent.get_refunded_work(checksum_address=self.checksum_address)
        return work

    @property
    def available_refund(self) -> int:
        refund_eth = self.worklock_agent.get_available_refund(checksum_address=self.checksum_address)
        return refund_eth

    @property
    def available_compensation(self) -> int:
        compensation_eth = self.worklock_agent.get_available_compensation(checksum_address=self.checksum_address)
        return compensation_eth

    @property
    def available_claim(self) -> int:
        tokens = self.worklock_agent.eth_to_tokens(self.get_deposited_eth)
        return tokens
