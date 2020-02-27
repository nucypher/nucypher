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
import time
from decimal import Decimal
from pathlib import Path
from typing import Tuple, List, Dict, Union

import click
import maya
from constant_sorrow.constants import (
    WORKER_NOT_RUNNING,
    NO_WORKER_ASSIGNED,
    BARE,
    IDLE,
    FULL
)
from eth_tester.exceptions import TransactionFailed
from eth_utils import keccak, is_checksum_address, to_checksum_address
from twisted.logger import Logger
from web3 import Web3
from web3.contract import ContractFunction

from nucypher.blockchain.economics import StandardTokenEconomics, EconomicsFactory, BaseEconomics
from nucypher.blockchain.eth.agents import (
    NucypherTokenAgent,
    StakingEscrowAgent,
    PolicyManagerAgent,
    AdjudicatorAgent,
    ContractAgency,
    PreallocationEscrowAgent,
    MultiSigAgent,
    WorkLockAgent)
from nucypher.blockchain.eth.decorators import validate_checksum_address, only_me, save_receipt
from nucypher.blockchain.eth.deployers import (
    NucypherTokenDeployer,
    StakingEscrowDeployer,
    PolicyManagerDeployer,
    StakingInterfaceDeployer,
    PreallocationEscrowDeployer,
    AdjudicatorDeployer,
    BaseContractDeployer,
    WorklockDeployer,
    SeederDeployer,
    MultiSigDeployer
)
from nucypher.blockchain.eth.interfaces import BlockchainDeployerInterface, BlockchainInterfaceFactory
from nucypher.blockchain.eth.interfaces import BlockchainInterface
from nucypher.blockchain.eth.multisig import Authorization
from nucypher.blockchain.eth.registry import (
    AllocationRegistry,
    BaseContractRegistry,
    IndividualAllocationRegistry
)
from nucypher.blockchain.eth.token import NU, Stake, StakeList, WorkTracker
from nucypher.blockchain.eth.utils import datetime_to_period, calculate_period_duration, datetime_at_period
from nucypher.characters.banners import STAKEHOLDER_BANNER
from nucypher.characters.control.emitters import StdoutEmitter
from nucypher.cli.painting import (
    paint_contract_deployment,
    paint_input_allocation_file,
    paint_deployed_allocations,
    write_deployed_allocations_to_csv
)
from nucypher.config.constants import DEFAULT_CONFIG_ROOT
from nucypher.crypto.powers import TransactingPower


class NucypherTokenActor:
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
        self.token_agent = ContractAgency.get_agent(NucypherTokenAgent, registry=self.registry)  # type: NucypherTokenAgent
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
        blockchain = BlockchainInterfaceFactory.get_interface()  # TODO: EthAgent?  #1509
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
        SeederDeployer
    )

    # For ownership relinquishment series.
    ownable_deployer_classes = (*dispatched_upgradeable_deployer_classes,
                                # SeederDeployer
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
                 staking_escrow_test_mode: bool = False,
                 economics: BaseEconomics = None):
        """
        Note: super() is not called here to avoid setting the token agent.
        TODO: Review this logic ^^ "bare mode".  #1510
        """
        self.log = Logger("Deployment-Actor")

        self.deployer_address = deployer_address
        self.checksum_address = self.deployer_address
        self.economics = economics or StandardTokenEconomics()

        self.registry = registry
        self.preallocation_escrow_deployers = dict()
        self.deployers = {d.contract_name: d for d in self.all_deployer_classes}

        self.deployer_power = TransactingPower(password=client_password, account=deployer_address, cache=True)
        self.transacting_power = self.deployer_power
        self.transacting_power.activate()
        self.staking_escrow_test_mode = staking_escrow_test_mode

        self.sidekick_power = None
        self.sidekick_address = None

    def __repr__(self):
        r = '{name} - {deployer_address})'.format(name=self.__class__.__name__, deployer_address=self.deployer_address)
        return r

    @validate_checksum_address
    def recruit_sidekick(self, sidekick_address: str, sidekick_password: str):
        self.sidekick_power = TransactingPower(account=sidekick_address, password=sidekick_password, cache=True)
        if self.sidekick_power.device:
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

        if len(secrets.values()) != len(set(secrets.values())):  # i.e., if there are duplicated secrets
            raise ValueError("You can't use the same secret for multiple contracts")

        return secrets

    def deploy_contract(self,
                        contract_name: str,
                        gas_limit: int = None,
                        plaintext_secret: str = None,
                        deployment_mode=FULL,
                        ignore_deployed: bool = False,
                        progress=None,
                        confirmations: int = 0,
                        deployment_parameters: dict = None,
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
            is_initial_deployment = deployment_mode != BARE  # i.e., we also deploy a dispatcher
            if is_initial_deployment and not plaintext_secret:
                raise ValueError("An upgrade secret must be passed to perform initial deployment of a Dispatcher.")
            secret_hash = None
            if plaintext_secret:
                secret_hash = keccak(bytes(plaintext_secret, encoding='utf-8'))
            receipts = deployer.deploy(secret_hash=secret_hash,
                                       gas_limit=gas_limit,
                                       progress=progress,
                                       ignore_deployed=ignore_deployed,
                                       confirmations=confirmations,
                                       deployment_mode=deployment_mode,
                                       **deployment_parameters)
        else:
            receipts = deployer.deploy(gas_limit=gas_limit,
                                       progress=progress,
                                       confirmations=confirmations,
                                       deployment_mode=deployment_mode,
                                       **deployment_parameters)
        return receipts, deployer

    def upgrade_contract(self,
                         contract_name: str,
                         existing_plaintext_secret: str,
                         new_plaintext_secret: str,
                         ignore_deployed: bool = False
                         ) -> dict:
        Deployer = self.__get_deployer(contract_name=contract_name)
        deployer = Deployer(registry=self.registry, deployer_address=self.deployer_address)
        new_secret_hash = keccak(bytes(new_plaintext_secret, encoding='utf-8'))
        receipts = deployer.upgrade(existing_secret_plaintext=bytes(existing_plaintext_secret, encoding='utf-8'),
                                    new_secret_hash=new_secret_hash,
                                    ignore_deployed=ignore_deployed)
        return receipts

    def retarget_proxy(self,
                       contract_name: str,
                       target_address: str,
                       existing_plaintext_secret: str,
                       new_plaintext_secret: str,
                       just_build_transaction: bool = False):
        Deployer = self.__get_deployer(contract_name=contract_name)
        deployer = Deployer(registry=self.registry, deployer_address=self.deployer_address)
        new_secret_hash = keccak(bytes(new_plaintext_secret, encoding='utf-8'))
        result = deployer.retarget(target_address=target_address,
                                   existing_secret_plaintext=bytes(existing_plaintext_secret, encoding='utf-8'),
                                   new_secret_hash=new_secret_hash,
                                   just_build_transaction=just_build_transaction)
        return result

    def rollback_contract(self, contract_name: str, existing_plaintext_secret: str, new_plaintext_secret: str):
        Deployer = self.__get_deployer(contract_name=contract_name)
        deployer = Deployer(registry=self.registry, deployer_address=self.deployer_address)
        new_secret_hash = keccak(bytes(new_plaintext_secret, encoding='utf-8'))
        receipts = deployer.rollback(existing_secret_plaintext=bytes(existing_plaintext_secret, encoding='utf-8'),
                                     new_secret_hash=new_secret_hash)
        return receipts

    def deploy_network_contracts(self,
                                 secrets: dict,
                                 interactive: bool = True,
                                 emitter: StdoutEmitter = None,
                                 etherscan: bool = False,
                                 ignore_deployed: bool = False) -> dict:
        """

        :param secrets: Contract upgrade secrets dictionary
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
                                                              progress=bar)
                else:
                    receipts, deployer = self.deploy_contract(contract_name=deployer_class.contract_name,
                                                              plaintext_secret=secrets[deployer_class.contract_name],
                                                              gas_limit=gas_limit,
                                                              progress=bar,
                                                              ignore_deployed=ignore_deployed)

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
                                     output_dir: str = None,
                                     crash_on_failure: bool = True,
                                     interactive: bool = True,
                                     emitter: StdoutEmitter = None,
                                     ) -> Dict[str, dict]:
        """
        The allocation file contains a list of allocations, each of them composed of:
          * 'beneficiary_address': Checksum address of the beneficiary
          * 'name': User-friendly name of the beneficiary (Optional)
          * 'amount': Amount of tokens locked, in NuNits
          * 'duration_seconds': Lock duration expressed in seconds

        It accepts both CSV and JSON formats. Example allocation file in CSV format:

        "beneficiary_address","name","amount","duration_seconds"
        "0xdeadbeef","H. E. Pennypacker",100,31536000
        "0xabced120","",133432,31536000
        "0xf7aefec2","",999,31536000

        Example allocation file in JSON format:

        [ {'beneficiary_address': '0xdeadbeef', 'name': 'H. E. Pennypacker', 'amount': 100, 'duration_seconds': 31536000},
          {'beneficiary_address': '0xabced120', 'amount': 133432, 'duration_seconds': 31536000},
          {'beneficiary_address': '0xf7aefec2', 'amount': 999, 'duration_seconds': 31536000}]

        """

        if interactive and not emitter:
            raise ValueError("'emitter' is a required keyword argument when interactive is True.")

        if allocation_registry and allocation_outfile:
            raise self.ActorError("Pass either allocation registry or allocation_outfile, not both.")
        if allocation_registry is None:
            allocation_registry = AllocationRegistry(filepath=allocation_outfile)

        if emitter:
            paint_input_allocation_file(emitter, allocations)

        if interactive:
            click.confirm("Continue with the allocation process?", abort=True)

        total_to_allocate = NU.from_nunits(sum(allocation['amount'] for allocation in allocations))
        balance = ContractAgency.get_agent(NucypherTokenAgent, self.registry).get_balance(self.deployer_address)
        if balance < total_to_allocate:
            raise ValueError(f"Not enough tokens to allocate. We need at least {total_to_allocate}.")

        allocation_receipts, failed, allocated = dict(), list(), list()
        total_deployment_transactions = len(allocations) * 4

        # Create an allocation template file, containing the allocation contract ABI and placeholder values
        # for the beneficiary and contract addresses. This file will be shared with all allocation users.
        empty_allocation_escrow_deployer = PreallocationEscrowDeployer(registry=self.registry)
        allocation_contract_abi = empty_allocation_escrow_deployer.get_contract_abi()
        allocation_template = {
            "BENEFICIARY_ADDRESS": ["ALLOCATION_CONTRACT_ADDRESS", allocation_contract_abi]
        }

        if not output_dir:
            output_dir = Path(allocation_registry.filepath).parent  # Use same folder as allocation registry
        template_filename = IndividualAllocationRegistry.REGISTRY_NAME
        template_filepath = os.path.join(output_dir, template_filename)
        AllocationRegistry(filepath=template_filepath).write(registry_data=allocation_template)
        if emitter:
            emitter.echo(f"Saved allocation template file to {template_filepath}", color='blue', bold=True)

        already_enrolled = [a['beneficiary_address'] for a in allocations
                            if allocation_registry.is_beneficiary_enrolled(a['beneficiary_address'])]
        if already_enrolled:
            raise ValueError(f"The following beneficiaries are already enrolled in allocation registry "
                             f"({allocation_registry.filepath}): {already_enrolled}")

        # Deploy each allocation contract
        with click.progressbar(length=total_deployment_transactions,
                               label="Allocation progress",
                               show_eta=False) as bar:
            bar.short_limit = 0
            for allocation in allocations:

                beneficiary = allocation['beneficiary_address']
                name = allocation.get('name', 'No name provided')

                if interactive:
                    click.pause(info=f"\nPress any key to continue with allocation for "
                                     f"beneficiary {beneficiary} ({name})")

                if emitter:
                    emitter.echo(f"\nDeploying PreallocationEscrow contract for beneficiary {beneficiary} ({name})...")
                    bar._last_line = None
                    bar.render_progress()

                amount = allocation['amount']
                duration = allocation['duration_seconds']

                try:
                    deployer = PreallocationEscrowDeployer(registry=self.registry,
                                                           deployer_address=self.deployer_address,
                                                           sidekick_address=self.sidekick_address,
                                                           allocation_registry=allocation_registry)

                    # 0 - Activate a TransactingPower (use the Sidekick if necessary)
                    use_sidekick = bool(self.sidekick_power)
                    if use_sidekick:
                        self.activate_sidekick(refresh=True)
                    else:
                        self.activate_deployer(refresh=True)

                    # 1 - Deploy the contract
                    deployer.deploy(use_sidekick=use_sidekick, progress=bar)

                    # 2 - Assign ownership to beneficiary
                    deployer.assign_beneficiary(checksum_address=beneficiary, use_sidekick=use_sidekick, progress=bar)

                    # 3 - Use main deployer account to do the initial deposit
                    self.activate_deployer(refresh=False)
                    deployer.initial_deposit(value=amount, duration_seconds=duration, progress=bar)

                    # 4 - Enroll in allocation registry
                    deployer.enroll_principal_contract()

                except TransactionFailed as e:
                    if crash_on_failure:
                        raise
                    message = f"Failed allocation transaction for {NU.from_nunits(amount)} to {beneficiary}: {e}"
                    self.log.debug(message)
                    if emitter:
                        emitter.echo(message=message, color='red', bold=True)
                    failed.append(allocation)
                    continue

                else:
                    allocation_receipts[beneficiary] = deployer.deployment_receipts
                    allocation_contract_address = deployer.contract_address
                    self.log.info(f"Created {deployer.contract_name} contract at {allocation_contract_address} "
                                  f"for beneficiary {beneficiary}.")
                    allocated.append((allocation, allocation_contract_address))

                    # Create individual allocation file
                    individual_allocation_filename = f'allocation-{beneficiary}.json'
                    individual_allocation_filepath = os.path.join(output_dir, individual_allocation_filename)
                    individual_allocation_file_data = {
                        'beneficiary_address': beneficiary,
                        'contract_address': allocation_contract_address
                    }
                    with open(individual_allocation_filepath, 'w') as outfile:
                        json.dump(individual_allocation_file_data, outfile)

                    if emitter:
                        blockchain = BlockchainInterfaceFactory.get_interface()
                        paint_contract_deployment(contract_name=deployer.contract_name,
                                                  receipts=deployer.deployment_receipts,
                                                  contract_address=deployer.contract_address,
                                                  emitter=emitter,
                                                  chain_name=blockchain.client.chain_name,
                                                  open_in_browser=False)
                        emitter.echo(f"Saved individual allocation file to {individual_allocation_filepath}",
                                     color='blue', bold=True)

            if emitter:
                paint_deployed_allocations(emitter, allocated, failed)

            csv_filename = f'allocation-summary-{self.deployer_address[:6]}-{maya.now().epoch}.csv'
            csv_filepath = os.path.join(output_dir, csv_filename)
            write_deployed_allocations_to_csv(csv_filepath, allocated, failed)
            if emitter:
                emitter.echo(f"Saved allocation summary CSV to {csv_filepath}", color='blue', bold=True)

            if failed:
                self.log.critical(f"FAILED TOKEN ALLOCATION - {len(failed)} allocations failed.")

        return allocation_receipts

    @staticmethod
    def __read_allocation_data(filepath: str) -> list:
        with open(filepath, 'r') as allocation_file:
            if filepath.endswith(".csv"):
                reader = csv.DictReader(allocation_file)
                allocation_data = list(reader)
            else:  # Assume it's JSON by default
                allocation_data = json.load(allocation_file)

        # Pre-process allocation data
        for entry in allocation_data:
            entry['beneficiary_address'] = to_checksum_address(entry['beneficiary_address'])
            entry['amount'] = int(entry['amount'])
            entry['duration_seconds'] = int(entry['duration_seconds'])

        return allocation_data

    def deploy_beneficiaries_from_file(self,
                                       allocation_data_filepath: str,
                                       allocation_outfile: str = None,
                                       emitter=None,
                                       interactive=None) -> dict:

        allocations = self.__read_allocation_data(filepath=allocation_data_filepath)
        receipts = self.deploy_beneficiary_contracts(allocations=allocations,
                                                     allocation_outfile=allocation_outfile,
                                                     emitter=emitter,
                                                     interactive=interactive,
                                                     crash_on_failure=False)
        # Save transaction metadata
        receipts_filepath = self.save_deployment_receipts(receipts=receipts, filename_prefix='allocation')
        if emitter:
            emitter.echo(f"Saved allocation receipts to {receipts_filepath}", color='blue', bold=True)
        return receipts

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

    def set_min_reward_rate_range(self,
                                  minimum: int,
                                  default: int,
                                  maximum: int,
                                  transaction_gas_limit: int = None) -> dict:

        policy_manager_deployer = PolicyManagerDeployer(registry=self.registry,
                                                        deployer_address=self.deployer_address,
                                                        economics=self.economics)
        receipt = policy_manager_deployer.set_min_reward_rate_range(minimum=minimum,
                                                                    default=default,
                                                                    maximum=maximum,
                                                                    gas_limit=transaction_gas_limit)
        return receipt


class MultiSigActor(NucypherTokenActor):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.multisig_agent = ContractAgency.get_agent(MultiSigAgent, registry=self.registry)  # type: MultiSigAgent


class Trustee(MultiSigActor):
    """
    A member of a MultiSigBoard given the power and
    obligation to execute an authorized transaction on
    behalf of the board of executives.
    """

    class NoAuthorizations(RuntimeError):
        """Raised when there are zero authorizations."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.authorizations = dict()

    def add_authorization(self, authorization):
        self.authorizations[authorization.trustee_address] = authorization

    def combine_authorizations(self) -> Tuple[List[bytes], ...]:
        if not self.authorizations:
            raise self.NoAuthorizations

        all_v, all_r, all_s = list(), list(), list()
        # Authorizations (i.e., signatures) must be provided in increasing order by signing address
        for trustee_address, authorization in sorted(self.authorizations.items()):
            v, r, s = authorization.get_components()
            all_v.append(v)
            all_r.append(r)
            all_s.append(s)

        # TODO: check for inconsistencies (nonce, etc.)
        return all_v, all_r, all_s

    def execute(self, contract_function: ContractFunction) -> dict:
        v, r, s = self.combine_authorizations()
        receipt = self.multisig_agent.execute(sender_address=self.checksum_address,
                                              v=v, r=r, s=s,
                                              transaction_function=contract_function,
                                              value=None)  # TODO: Design Flaw...
        return receipt

    def change_threshold(self, new_threshold: int) -> dict:
        # TODO: Implement Agent method for change threshold for function binding
        receipt = self.multisig_agent.execute()
        return receipt

    def produce_data_to_sign(self, transaction):
        data_to_sign = dict(trustee_address=transaction['from'],
                            target_address=transaction['to'],
                            value=transaction['value'],
                            data=transaction['data'],
                            nonce=self.multisig_agent.nonce)

        unsigned_digest = self.multisig_agent.get_unsigned_transaction_hash(**data_to_sign)

        data_for_multisig_executives = {
            'parameters': data_to_sign,
            'digest': unsigned_digest.hex()
        }

        return data_for_multisig_executives


class Executive(MultiSigActor):
    """
    An actor having the power to authorize transaction executions to a delegated trustee.
    """

    def sign_hash(self, unsigned_hash: bytes) -> bytes:
        blockchain = self.multisig_agent.blockchain
        signed_hash = blockchain.transacting_power.sign_hash(unsigned_hash=unsigned_hash)
        return signed_hash

    def authorize(self, trustee, contract_function: ContractFunction) -> Authorization:
        try:
            transaction = contract_function.buildTransaction()
        except (TransactionFailed, ValueError):
            # TODO - Handle Validation Failure
            raise
        unsigned_transaction_hash = self.multisig_agent.get_unsigned_transaction_hash(
            trustee_address=trustee.checksum_address,
            target_address=contract_function.address,
            value=transaction['value'],
            data=transaction['data'],
            nonce=trustee.current_nonce
        )
        signed_transaction_hash = self.sign_hash(unsigned_hash=unsigned_transaction_hash)
        authorization = self.Authorization(trustee_address=trustee.checksum_address,
                                           signed_transaction_hash=signed_transaction_hash)
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
        self.policy_agent = ContractAgency.get_agent(PolicyManagerAgent, registry=self.registry)   # type: PolicyManagerAgent
        self.staking_agent = ContractAgency.get_agent(StakingEscrowAgent, registry=self.registry)  # type: StakingEscrowAgent
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

    @property
    def is_contract(self) -> bool:
        return self.preallocation_escrow_agent is not None

    def to_dict(self) -> dict:
        stake_info = [stake.to_stake_info() for stake in self.stakes]
        worker_address = self.worker_address or BlockchainInterface.NULL_ADDRESS
        staker_funds = {'ETH': int(self.eth_balance), 'NU': int(self.token_balance)}
        staker_payload = {'staker': self.checksum_address,
                          'balances': staker_funds,
                          'worker': worker_address,
                          'stakes': stake_info}
        return staker_payload

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
        The total number of staked tokens, i.e., tokens locked in the current period.
        """
        return self.locked_tokens(periods=0)

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
                         amount: NU = None,
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
        elif not entire_balance and not amount:
            raise ValueError("Specify an amount or entire balance, got neither")

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

    @only_me
    def prolong_stake(self,
                      stake_index: int,
                      additional_periods: int = None,
                      expiration: maya.MayaDT = None) -> tuple:

        # Calculate duration in periods
        if additional_periods and expiration:
            raise ValueError("Pass the number of lock periods or an expiration MayaDT; not both.")

        # Update staking cache element
        stakes = self.stakes

        # Select stake to prolong from local cache
        try:
            current_stake = stakes[stake_index]
        except KeyError:
            if len(stakes):
                message = f"Cannot prolong stake - No stake exists with index {stake_index}."
            else:
                message = "Cannot prolong stake - There are no active stakes."
            raise Stake.StakingError(message)

        # Calculate stake duration in periods
        if expiration:
            additional_periods = datetime_to_period(datetime=expiration, seconds_per_period=self.economics.seconds_per_period) - current_stake.final_locked_period
            if additional_periods <= 0:
                raise Stake.StakingError(f"New expiration {expiration} must be at least 1 period from the "
                                         f"current stake's end period ({current_stake.final_locked_period}).")

        stake = current_stake.prolong(additional_periods=additional_periods)

        # Update staking cache element
        self.stakes.refresh()
        return stake

    def deposit(self, amount: int, lock_periods: int) -> Tuple[str, str]:
        """Public facing method for token locking."""
        if self.is_contract:
            receipt = self.preallocation_escrow_agent.deposit_as_staker(amount=amount, lock_periods=lock_periods)
        else:
            receipt = self.token_agent.approve_and_call(amount=amount,
                                                        target_address=self.staking_agent.contract_address,
                                                        sender_address=self.checksum_address,
                                                        call_data=Web3.toBytes(lock_periods))
        return receipt

    @property
    def is_restaking(self) -> bool:
        restaking = self.staking_agent.is_restaking(staker_address=self.checksum_address)
        return restaking

    @only_me
    @save_receipt
    def _set_restaking(self, value: bool) -> dict:
        if self.is_contract:
            receipt = self.preallocation_escrow_agent.set_restaking(value=value)
        else:
            receipt = self.staking_agent.set_restaking(staker_address=self.checksum_address, value=value)
        return receipt

    def enable_restaking(self) -> dict:
        receipt = self._set_restaking(value=True)
        return receipt

    @only_me
    @save_receipt
    def enable_restaking_lock(self, release_period: int):
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

    def disable_restaking(self) -> dict:
        receipt = self._set_restaking(value=False)
        return receipt

    @property
    def is_winding_down(self) -> bool:
        winding_down = self.staking_agent.is_winding_down(staker_address=self.checksum_address)
        return winding_down

    @only_me
    @save_receipt
    def _set_winding_down(self, value: bool) -> dict:
        if self.is_contract:
            receipt = self.preallocation_escrow_agent.set_winding_down(value=value)
        else:
            receipt = self.staking_agent.set_winding_down(staker_address=self.checksum_address, value=value)
        return receipt

    def enable_winding_down(self) -> dict:
        receipt = self._set_winding_down(value=True)
        return receipt

    def disable_winding_down(self) -> dict:
        receipt = self._set_winding_down(value=False)
        return receipt

    #
    # Bonding with Worker
    #

    @only_me
    @save_receipt
    @validate_checksum_address
    def set_worker(self, worker_address: str) -> dict:
        if self.is_contract:
            receipt = self.preallocation_escrow_agent.set_worker(worker_address=worker_address)
        else:
            receipt = self.staking_agent.set_worker(staker_address=self.checksum_address,
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

        if self.__worker_address == BlockchainInterface.NULL_ADDRESS:
            return NO_WORKER_ASSIGNED.bool_value(False)
        return self.__worker_address

    @only_me
    @save_receipt
    def detach_worker(self) -> dict:
        if self.is_contract:
            receipt = self.preallocation_escrow_agent.release_worker()
        else:
            receipt = self.staking_agent.release_worker(staker_address=self.checksum_address)
        self.__worker_address = BlockchainInterface.NULL_ADDRESS
        return receipt

    #
    # Reward and Collection
    #

    @only_me
    @save_receipt
    def mint(self) -> Tuple[str, str]:
        """Computes and transfers tokens to the staker's account"""
        if self.is_contract:
            receipt = self.preallocation_escrow_agent.mint()
        else:
            receipt = self.staking_agent.mint(staker_address=self.checksum_address)
        return receipt

    def calculate_staking_reward(self) -> int:
        staking_reward = self.staking_agent.calculate_staking_reward(staker_address=self.checksum_address)
        return staking_reward

    def calculate_policy_reward(self) -> int:
        policy_reward = self.policy_agent.get_reward_amount(staker_address=self.checksum_address)
        return policy_reward

    @only_me
    @save_receipt
    @validate_checksum_address
    def collect_policy_reward(self, collector_address=None) -> dict:
        """Collect rewarded ETH."""
        if self.is_contract:
            withdraw_address = collector_address or self.beneficiary_address
            receipt = self.preallocation_escrow_agent.collect_policy_reward(collector_address=withdraw_address)
        else:
            withdraw_address = collector_address or self.checksum_address
            receipt = self.policy_agent.collect_policy_reward(collector_address=withdraw_address,
                                                              staker_address=self.checksum_address)
        return receipt

    @only_me
    @save_receipt
    def collect_staking_reward(self) -> dict:
        """Withdraw tokens rewarded for staking."""
        if self.is_contract:
            reward_amount = self.calculate_staking_reward()
            self.log.debug(f"Withdrawing staking reward ({NU.from_nunits(reward_amount)}) to {self.checksum_address}")
            receipt = self.preallocation_escrow_agent.withdraw_as_staker(value=reward_amount)
        else:
            receipt = self.staking_agent.collect_staking_reward(staker_address=self.checksum_address)
        return receipt

    @only_me
    @save_receipt
    def withdraw(self, amount: NU) -> dict:
        """Withdraw tokens from StakingEscrow (assuming they're unlocked)"""
        if self.is_contract:
            receipt = self.preallocation_escrow_agent.withdraw_as_staker(value=int(amount))
        else:
            receipt = self.staking_agent.withdraw(staker_address=self.checksum_address,
                                                  amount=int(amount))
        return receipt

    @only_me
    @save_receipt
    def withdraw_preallocation_tokens(self, amount: NU) -> dict:
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
    def withdraw_preallocation_eth(self) -> dict:
        """Withdraw ETH from PreallocationEscrow"""
        if self.is_contract:
            receipt = self.preallocation_escrow_agent.withdraw_eth()
        else:
            raise TypeError("This method can only be used when staking via a contract")
        return receipt

    @property
    def missing_confirmations(self) -> int:
        staker_address = self.checksum_address
        missing = self.staking_agent.get_missing_confirmations(checksum_address=staker_address)
        return missing

    @only_me
    @save_receipt
    def set_min_reward_rate(self, min_rate: int) -> Tuple[str, str]:
        """Public facing method for setting min reward rate."""
        minimum, _default, maximum = self.policy_agent.get_min_reward_rate_range()
        if min_rate < minimum or min_rate > maximum:
            raise ValueError(f"Min reward rate  {min_rate} must be within range [{minimum}, {maximum}]")
        if self.is_contract:
            receipt = self.preallocation_escrow_agent.set_min_reward_rate(min_rate=min_rate)
        else:
            receipt = self.policy_agent.set_min_reward_rate(staker_address=self.checksum_address, min_rate=min_rate)
        return receipt

    @property
    def min_reward_rate(self) -> int:
        """Minimum acceptable reward rate"""
        staker_address = self.checksum_address
        min_rate = self.policy_agent.get_min_reward_rate(staker_address)
        return min_rate

    @property
    def raw_min_reward_rate(self) -> int:
        """Minimum acceptable reward rate set by staker.
        This's not applicable if this rate out of global range.
        In that case default value will be used instead of raw value (see `min_reward_rate`)"""

        staker_address = self.checksum_address
        min_rate = self.policy_agent.get_raw_min_reward_rate(staker_address)
        return min_rate


class Worker(NucypherTokenActor):
    """
    Ursula baseclass for blockchain operations, practically carrying a pickaxe.
    """

    BONDING_TIMEOUT = None  # (None or 0) == indefinite
    BONDING_POLL_RATE = 10

    class WorkerError(NucypherTokenActor.ActorError):
        pass

    class DetachedWorker(WorkerError):
        """Raised when the Worker is not bonded to a Staker in the StakingEscrow contract."""

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

        self._checksum_address = None  # Stake Address
        self.__worker_address = worker_address

        # Agency
        self.staking_agent = ContractAgency.get_agent(StakingEscrowAgent, registry=self.registry)

        # Someday, when we have Workers for tasks other than PRE, this might instead be composed on Ursula.
        self.policy_agent = ContractAgency.get_agent(PolicyManagerAgent, registry=self.registry)

        # Stakes
        self.__start_time = WORKER_NOT_RUNNING
        self.__uptime_period = WORKER_NOT_RUNNING

        # Workers cannot be started without being assigned a stake first.
        if is_me:
            if block_until_ready:
                self.block_until_ready()
            self.stakes = StakeList(registry=self.registry, checksum_address=self.checksum_address)
            self.stakes.refresh()

            self.work_tracker = work_tracker or WorkTracker(worker=self)
            if start_working_now:
                self.work_tracker.start(act_now=False)

    def block_until_ready(self, poll_rate: int = None, timeout: int = None):
        """
        Polls the staking_agent and blocks until the staking address is not
        a null address for the given worker_address. Once the worker is bonded, it returns the staker address.
        """
        if not self.__worker_address:
            raise RuntimeError("No worker address available")

        timeout = timeout or self.BONDING_TIMEOUT
        poll_rate = poll_rate or self.BONDING_POLL_RATE
        staking_agent = ContractAgency.get_agent(StakingEscrowAgent, registry=self.registry)
        client = staking_agent.blockchain.client
        start = maya.now()

        emitter = StdoutEmitter()  # TODO: Make injectable, or embed this logic into Ursula
        emitter.message("Waiting for bonding and funding...")

        funded, bonded = False, False
        while True:

            # Read
            staking_address = staking_agent.get_staker_from_worker(self.__worker_address)
            ether_balance = client.get_balance(self.__worker_address)

            # Bonding
            if (not bonded) and (staking_address != BlockchainInterface.NULL_ADDRESS):
                bonded = True
                emitter.message(f"Worker is bonded to ({staking_address})!", color='green', bold=True)

            # Balance
            if ether_balance and (not funded):
                funded, balance = True, Web3.fromWei(ether_balance, 'ether')
                emitter.message(f"Worker is funded with {balance} ETH!", color='green', bold=True)

            # Success and Escape
            if staking_address != BlockchainInterface.NULL_ADDRESS and ether_balance:
                self._checksum_address = staking_address
                emitter.message(f"Starting services...", color='yellow', bold=True)
                break

            # Crash on Timeout
            if timeout:
                now = maya.now()
                delta = now - start
                if delta.total_seconds() >= timeout:
                    if staking_address == BlockchainInterface.NULL_ADDRESS:
                        raise self.DetachedWorker(f"Worker {self.__worker_address} not bonded after waiting {timeout} seconds.")
                    elif not ether_balance:
                        raise RuntimeError(f"Worker {self.__worker_address} has no ether after waiting {timeout} seconds.")

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
    def last_active_period(self) -> int:
        period = self.staking_agent.get_last_active_period(staker_address=self.checksum_address)
        return period

    @only_me
    @save_receipt
    def confirm_activity(self) -> dict:
        """For each period that the worker confirms activity, the staker is rewarded"""
        receipt = self.staking_agent.confirm_activity(worker_address=self.__worker_address)
        return receipt

    @property
    def missing_confirmations(self) -> int:
        staker_address = self.checksum_address
        missing = self.staking_agent.get_missing_confirmations(checksum_address=staker_address)
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
        _minimum, default, _maximum = self.policy_agent.get_min_reward_rate_range()
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
            now = self.staking_agent.blockchain.w3.eth.getBlock(block_identifier='latest').timestamp
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


class StakeHolder(Staker):

    banner = STAKEHOLDER_BANNER

    class StakingWallet:

        class UnknownAccount(KeyError):
            pass

        def __init__(self,
                     registry: BaseContractRegistry,
                     checksum_addresses: set = None):

            # Wallet
            self.__accounts = set()  # Note: Account index is meaningless here
            self.__transacting_powers = dict()

            # Blockchain
            self.registry = registry
            self.blockchain = BlockchainInterfaceFactory.get_interface()
            self.token_agent = ContractAgency.get_agent(NucypherTokenAgent, registry=self.registry)

            self.__get_accounts()
            if checksum_addresses:
                self.__accounts.update(checksum_addresses)

        @validate_checksum_address
        def __contains__(self, checksum_address: str) -> bool:
            return bool(checksum_address in self.__accounts)

        @property
        def active_account(self) -> str:
            return self.blockchain.transacting_power.account

        def __get_accounts(self) -> None:
            accounts = self.blockchain.client.accounts
            self.__accounts.update(accounts)

        @property
        def accounts(self) -> set:
            return self.__accounts

        @validate_checksum_address
        def activate_account(self, checksum_address: str, password: str = None) -> None:
            if checksum_address not in self:
                self.__get_accounts()
                if checksum_address not in self:
                    raise self.UnknownAccount
            try:
                transacting_power = self.__transacting_powers[checksum_address]
            except KeyError:
                transacting_power = TransactingPower(password=password, account=checksum_address)
                self.__transacting_powers[checksum_address] = transacting_power
            transacting_power.activate(password=password)

        @property
        def balances(self) -> Dict:
            balances = dict()
            for account in self.accounts:
                funds = {'ETH': self.blockchain.client.get_balance(account),
                         'NU': self.token_agent.get_balance(account)}
                balances.update({account: funds})
            return balances

    #
    # StakeHolder
    #

    def __init__(self,
                 is_me: bool = True,
                 initial_address: str = None,
                 checksum_addresses: set = None,
                 password: str = None,
                 *args, **kwargs):

        self.staking_interface_agent = None

        super().__init__(is_me=is_me, checksum_address=initial_address, *args, **kwargs)
        self.log = Logger(f"stakeholder")

        # Wallet
        self.wallet = self.StakingWallet(registry=self.registry, checksum_addresses=checksum_addresses)
        if initial_address:
            # If an initial address was passed,
            # it is safe to understand that it has already been used at a higher level.
            if initial_address not in self.wallet:
                message = f"Account {initial_address} is not known by this Ethereum client. Is it a HW account? " \
                          f"If so, make sure that your device is plugged in and you use the --hw-wallet flag."
                raise self.StakingWallet.UnknownAccount(message)
            self.assimilate(checksum_address=initial_address, password=password)

    @validate_checksum_address
    def assimilate(self, checksum_address: str, password: str = None) -> None:
        if self.is_contract:
            original_form = f"{self.beneficiary_address[0:8]} (contract {self.checksum_address[0:8]})"
        else:
            original_form = self.checksum_address

        # This handles both regular staking and staking via a contract
        if self.individual_allocation:
            if checksum_address != self.individual_allocation.beneficiary_address:
                raise ValueError(f"Beneficiary {self.individual_allocation.beneficiary_address} in individual "
                                 f"allocation doesn't match this checksum address ({checksum_address})")
            staking_address = self.individual_allocation.contract_address
            self.beneficiary_address = self.individual_allocation.beneficiary_address
            self.preallocation_escrow_agent = PreallocationEscrowAgent(registry=self.registry,
                                                                       allocation_registry=self.individual_allocation,
                                                                       beneficiary=self.beneficiary_address)
        else:
            staking_address = checksum_address
            self.beneficiary_address = None
            self.preallocation_escrow_agent = None

        self.wallet.activate_account(checksum_address=checksum_address, password=password)
        self.checksum_address = staking_address
        self.stakes = StakeList(registry=self.registry, checksum_address=staking_address)
        self.stakes.refresh()

        if self.is_contract:
            new_form = f"{self.beneficiary_address[0:8]} (contract {self.checksum_address[0:8]})"
        else:
            new_form = self.checksum_address

        self.log.info(f"Resistance is futile - Assimilating Staker {original_form} -> {new_form}.")

    @property
    def all_stakes(self) -> list:
        stakes = list()
        for account in self.wallet.accounts:
            more_stakes = StakeList(registry=self.registry, checksum_address=account)
            more_stakes.refresh()
            stakes.extend(more_stakes)
        return stakes

    @validate_checksum_address
    def get_staker(self, checksum_address: str):
        if checksum_address not in self.wallet.accounts:
            raise ValueError(f"{checksum_address} is not a known client account.")
        staker = Staker(is_me=True, checksum_address=checksum_address, registry=self.registry)
        staker.stakes.refresh()
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

    class BidingIsClosed(BidderError):
        pass

    @validate_checksum_address
    def __init__(self,
                 checksum_address: str,
                 is_transacting: bool = True,
                 client_password: str = None,
                 *args, **kwargs):
        super().__init__(checksum_address=checksum_address, *args, **kwargs)
        self.worklock_agent = ContractAgency.get_agent(WorkLockAgent, registry=self.registry)
        self.staking_agent = ContractAgency.get_agent(StakingEscrowAgent, registry=self.registry)
        self.economics = EconomicsFactory.get_economics(registry=self.registry)

        if is_transacting:
            self.transacting_power = TransactingPower(password=client_password, account=checksum_address)
            self.transacting_power.activate()

    def _ensure_bidding_is_open(self) -> None:
        highest_block = self.worklock_agent.blockchain.w3.eth.getBlock('latest')
        now = highest_block['timestamp']
        start = self.worklock_agent.start_date
        end = self.worklock_agent.end_date
        if now < start:
            raise self.BiddingIsClosed(f'Bidding does not open until {maya.MayaDT(start).slang_date()}')
        if now > end:
            raise self.BiddingIsClosed(f'Bidding closed at {maya.MayaDT(end).slang_date()}')

    def _ensure_bidding_is_closed(self, message: str = None) -> None:
        highest_block = self.worklock_agent.blockchain.w3.eth.getBlock('latest')
        now = highest_block['timestamp']
        end = self.worklock_agent.end_date
        if now < end:
            message = message or f"Bidding does not close until {end}"
            raise self.BiddingIsOpen(message)

    #
    # Transactions
    #

    def place_bid(self, value: int) -> dict:
        self._ensure_bidding_is_open()
        receipt = self.worklock_agent.bid(checksum_address=self.checksum_address, value=value)
        return receipt

    def claim(self) -> dict:

        # Require the Bidding window is closed
        end = self.worklock_agent.end_date
        error = f"Claims cannot be placed while the bidding window is still open (closes at {end})."
        self._ensure_bidding_is_closed(message=error)

        # Ensure the claim was not already placed
        if self._has_claimed:
            raise self.BidderError(f"Bidder {self.checksum_address} already placed a claim.")

        # Require an active bid
        if not self.get_deposited_eth:
            raise self.BidderError(f"No claims available for {self.checksum_address}")

        # Ensure the claim is at least large enough for min. stake
        minimum = self.economics.minimum_allowed_locked
        if self.available_claim < minimum:
            raise ValueError(f"Claim is too small. Claim amount must be worth at least {NU.from_nunits(minimum)})")

        receipt = self.worklock_agent.claim(checksum_address=self.checksum_address)
        return receipt

    def cancel_bid(self) -> dict:

        # Require an active bid
        if not self.get_deposited_eth:
            self.BidderError(f"No bids available for {self.checksum_address}")

        # Ensure the claim was not already placed
        if self._has_claimed:
            raise self.BidderError(f"Bidder {self.checksum_address} already placed a claim.")

        receipt = self.worklock_agent.cancel_bid(checksum_address=self.checksum_address)
        return receipt

    def refund_deposit(self) -> dict:
        """Refund ethers for completed work"""
        if not self.available_refund:
            raise self.BidderError(f'There is no refund available for {self.checksum_address}')
        receipt = self.worklock_agent.refund(checksum_address=self.checksum_address)
        return receipt

    #
    # Calls
    #

    @property
    def get_deposited_eth(self, denomination: str = 'wei') -> int:
        bid = self.worklock_agent.get_deposited_eth(checksum_address=self.checksum_address)
        ether_bid = Web3.toWei(bid, denomination)
        return ether_bid

    @property
    def _has_claimed(self) -> bool:
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
        except (TransactionFailed, ValueError):  # TODO: Is his how we want to handle thid?
            work = 0
        return work

    @property
    def refunded_work(self) -> int:
        work = self.worklock_agent.get_refunded_work(checksum_address=self.checksum_address)
        return work

    @property
    def available_refund(self) -> int:
        refund_eth = self.worklock_agent.get_available_refund(completed_work=self.completed_work)
        bid = self.get_deposited_eth
        if refund_eth > bid:
            # Overachiever: This bidder has worked more than required.
            refund_eth = bid
        return refund_eth

    @property
    def available_claim(self) -> int:
        tokens = self.worklock_agent.eth_to_tokens(self.get_deposited_eth)
        return tokens
