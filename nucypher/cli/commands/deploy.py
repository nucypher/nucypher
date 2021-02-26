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

import click
from constant_sorrow import constants
from typing import Tuple

from nucypher.blockchain.eth.actors import ContractAdministrator, Trustee
from nucypher.blockchain.eth.agents import ContractAgency, MultiSigAgent
from nucypher.blockchain.eth.clients import PUBLIC_CHAINS
from nucypher.blockchain.eth.constants import STAKING_ESCROW_CONTRACT_NAME
from nucypher.blockchain.eth.interfaces import BlockchainInterface
from nucypher.blockchain.eth.networks import NetworksInventory
from nucypher.blockchain.eth.registry import (
    BaseContractRegistry,
    GithubRegistrySource,
    InMemoryContractRegistry,
    RegistrySourceManager
)
from nucypher.blockchain.eth.signers.base import Signer
from nucypher.blockchain.eth.signers.software import ClefSigner
from nucypher.blockchain.eth.sol.__conf__ import SOLIDITY_COMPILER_VERSION
from nucypher.characters.control.emitters import StdoutEmitter
from nucypher.cli.actions.auth import get_client_password
from nucypher.cli.actions.confirm import confirm_deployment, verify_upgrade_details
from nucypher.cli.actions.select import select_client_account
from nucypher.cli.config import group_general_config
from nucypher.cli.literature import (
    CANNOT_OVERWRITE_REGISTRY,
    CONFIRM_BEGIN_UPGRADE,
    CONFIRM_BUILD_RETARGET_TRANSACTION,
    CONFIRM_MANUAL_REGISTRY_DOWNLOAD,
    CONFIRM_NETWORK_ACTIVATION,
    CONFIRM_RETARGET,
    CONFIRM_SELECTED_ACCOUNT,
    CONTRACT_DEPLOYMENT_SERIES_BEGIN_ADVISORY,
    CONTRACT_IS_NOT_OWNABLE,
    DEPLOYER_ADDRESS_ZERO_ETH,
    DEPLOYER_BALANCE,
    MINIMUM_POLICY_RATE_EXCEEDED_WARNING,
    PROMPT_NEW_OWNER_ADDRESS,
    REGISTRY_NOT_AVAILABLE,
    SELECT_DEPLOYER_ACCOUNT,
    SUCCESSFUL_REGISTRY_CREATION,
    SUCCESSFUL_REGISTRY_DOWNLOAD,
    SUCCESSFUL_RETARGET,
    SUCCESSFUL_RETARGET_TX_BUILT,
    SUCCESSFUL_SAVE_MULTISIG_TX_PROPOSAL,
    SUCCESSFUL_UPGRADE,
    UNKNOWN_CONTRACT_NAME,
    DEPLOYER_IS_NOT_OWNER,
    REGISTRY_PUBLICATION_HINT,
    ETHERSCAN_VERIFY_HINT
)
from nucypher.cli.options import (
    group_options,
    option_config_root,
    option_contract_name,
    option_etherscan,
    option_force,
    option_hw_wallet,
    option_network,
    option_poa,
    option_provider_uri,
    option_signer_uri,
    option_parameters, option_gas_strategy, option_max_gas_price)
from nucypher.cli.painting.deployment import (
    paint_contract_deployment,
    paint_deployer_contract_inspection,
    paint_staged_deployment
)
from nucypher.cli.painting.help import echo_solidity_version
from nucypher.cli.painting.multisig import paint_multisig_proposed_transaction
from nucypher.cli.painting.transactions import paint_receipt_summary
from nucypher.cli.types import EIP55_CHECKSUM_ADDRESS, EXISTING_READABLE_FILE, WEI
from nucypher.cli.utils import (
    deployer_pre_launch_warnings,
    ensure_config_root,
    establish_deployer_registry,
    initialize_deployer_interface
)
from nucypher.crypto.powers import TransactingPower

option_deployer_address = click.option('--deployer-address', help="Deployer's checksum address", type=EIP55_CHECKSUM_ADDRESS)
option_registry_infile = click.option('--registry-infile', help="Input path for contract registry file", type=EXISTING_READABLE_FILE)
option_registry_outfile = click.option('--registry-outfile', help="Output path for contract registry file", type=click.Path(file_okay=True))
option_target_address = click.option('--target-address', help="Address of the target contract", type=EIP55_CHECKSUM_ADDRESS)
option_gas = click.option('--gas', help="Operate with a specified gas per-transaction limit", type=click.IntRange(min=1))
option_ignore_deployed = click.option('--ignore-deployed', help="Ignore already deployed contracts if exist.", is_flag=True)
option_ignore_solidity_version = click.option('--ignore-solidity-check', help="Ignore solidity version compatibility check", is_flag=True)
option_confirmations = click.option('--confirmations', help="Number of block confirmations to wait between transactions", type=click.IntRange(min=0), default=3)


class ActorOptions:

    __option_name__ = 'actor_options'

    def __init__(self,
                 provider_uri: str,
                 deployer_address: str,
                 contract_name: str,
                 registry_infile: str,
                 registry_outfile: str,
                 hw_wallet: bool,
                 dev: bool,
                 force: bool,
                 poa: bool,
                 config_root: str,
                 etherscan: bool,
                 ignore_solidity_check,
                 gas_strategy: str,
                 max_gas_price: int,  # gwei
                 signer_uri: str,
                 network: str
                 ):

        self.provider_uri = provider_uri
        self.signer_uri = signer_uri
        self.gas_strategy = gas_strategy
        self.max_gas_price = max_gas_price
        self.deployer_address = deployer_address
        self.contract_name = contract_name
        self.registry_infile = registry_infile
        self.registry_outfile = registry_outfile
        self.hw_wallet = hw_wallet
        self.dev = dev
        self.force = force
        self.config_root = config_root
        self.etherscan = etherscan
        self.poa = poa
        self.ignore_solidity_check = ignore_solidity_check
        self.network = network

    def create_actor(self,
                     emitter: StdoutEmitter,
                     is_multisig: bool = False
                     ) -> Tuple[ContractAdministrator, str, BlockchainInterface, BaseContractRegistry]:

        ensure_config_root(self.config_root)
        deployer_interface = initialize_deployer_interface(poa=self.poa,
                                                           provider_uri=self.provider_uri,
                                                           emitter=emitter,
                                                           ignore_solidity_check=self.ignore_solidity_check,
                                                           gas_strategy=self.gas_strategy,
                                                           max_gas_price=self.max_gas_price)

        # Warnings
        deployer_pre_launch_warnings(emitter, self.etherscan, self.hw_wallet)

        #
        # Establish Registry
        #

        local_registry = establish_deployer_registry(emitter=emitter,
                                                     use_existing_registry=bool(self.contract_name),  # TODO: Issue #2314
                                                     registry_infile=self.registry_infile,
                                                     registry_outfile=self.registry_outfile,
                                                     dev=self.dev,
                                                     network=self.network)
        #
        # Make Authenticated Deployment Actor
        #

        # Verify Address & collect password
        if is_multisig:
            multisig_agent = ContractAgency.get_agent(MultiSigAgent, registry=local_registry)
            deployer_address = multisig_agent.contract.address
            transacting_power = None

        else:
            testnet = deployer_interface.client.chain_name != PUBLIC_CHAINS[1]  # Mainnet
            signer = Signer.from_signer_uri(self.signer_uri, testnet=testnet)
            deployer_address = self.deployer_address
            if not deployer_address:
                deployer_address = select_client_account(emitter=emitter,
                                                         prompt=SELECT_DEPLOYER_ACCOUNT,
                                                         registry=local_registry,
                                                         provider_uri=self.provider_uri,
                                                         signer=signer,
                                                         show_eth_balance=True)

            if not self.force:
                click.confirm(CONFIRM_SELECTED_ACCOUNT.format(address=deployer_address), abort=True)

            # Authenticate
            is_clef = ClefSigner.is_valid_clef_uri(self.signer_uri)
            password_required = all((not is_clef,
                                     not signer.is_device(account=deployer_address),
                                     not deployer_interface.client.is_local,
                                     not self.hw_wallet))
            if password_required:
                password = get_client_password(checksum_address=deployer_address)
                signer.unlock_account(password=password, account=deployer_address)
            transacting_power = TransactingPower(signer=signer, account=deployer_address)

        # Produce Actor
        ADMINISTRATOR = ContractAdministrator(registry=local_registry,
                                              domain=self.network,
                                              transacting_power=transacting_power)

        # Verify ETH Balance
        emitter.echo(DEPLOYER_BALANCE.format(eth_balance=ADMINISTRATOR.eth_balance))
        if transacting_power and ADMINISTRATOR.eth_balance == 0:
            emitter.echo(DEPLOYER_ADDRESS_ZERO_ETH, color='red', bold=True)
            raise click.Abort()
        return ADMINISTRATOR, deployer_address, deployer_interface, local_registry


group_actor_options = group_options(
    ActorOptions,
    provider_uri=option_provider_uri(),
    gas_strategy=option_gas_strategy,
    max_gas_price=option_max_gas_price,
    signer_uri=option_signer_uri,
    contract_name=option_contract_name(required=False),  # TODO: Make this required see Issue #2314
    poa=option_poa,
    force=option_force,
    hw_wallet=option_hw_wallet,
    deployer_address=option_deployer_address,
    registry_infile=option_registry_infile,
    registry_outfile=option_registry_outfile,
    dev=click.option('--dev', '-d', help="Forcibly use the development registry filepath.", is_flag=True),
    config_root=option_config_root,
    etherscan=option_etherscan,
    ignore_solidity_check=option_ignore_solidity_version,
    network=option_network(required=True)
)


@click.group()
@click.option('--solidity-version',
              help="Echo the supported solidity version.",
              is_flag=True,
              callback=echo_solidity_version,
              expose_value=False,
              is_eager=True)
def deploy():
    """Manage contract and registry deployment."""


@deploy.command(name='download-registry')
@group_general_config
@option_config_root
@option_registry_outfile
@option_network(default=NetworksInventory.DEFAULT, validate=True)  # TODO: See 2214
@option_force
def download_registry(general_config, config_root, registry_outfile, network, force):
    """Download the latest registry."""

    # Setup
    emitter = general_config.emitter
    ensure_config_root(config_root)
    github_source = GithubRegistrySource(network=network, registry_name=BaseContractRegistry.REGISTRY_NAME)
    source_manager = RegistrySourceManager(sources=[github_source])

    if not force:
        prompt = CONFIRM_MANUAL_REGISTRY_DOWNLOAD.format(source=github_source)
        click.confirm(prompt, abort=True)
    try:
        registry = InMemoryContractRegistry.from_latest_publication(source_manager=source_manager, network=network)
    except RegistrySourceManager.NoSourcesAvailable:
        emitter.message(REGISTRY_NOT_AVAILABLE, color="red")
        raise click.Abort

    try:
        output_filepath = registry.commit(filepath=registry_outfile, overwrite=force)
    except InMemoryContractRegistry.CantOverwriteRegistry:
        emitter.message(CANNOT_OVERWRITE_REGISTRY, color="red")
        raise click.Abort
    emitter.message(SUCCESSFUL_REGISTRY_DOWNLOAD.format(output_filepath=output_filepath))


@deploy.command()
@group_general_config
@option_provider_uri(required=True)
@option_config_root
@option_registry_infile
@option_deployer_address
@option_poa
@option_network(required=False, default=NetworksInventory.DEFAULT)
@option_ignore_solidity_version
def inspect(general_config, provider_uri, config_root, registry_infile, deployer_address,
            poa, ignore_solidity_check, network):
    """Echo owner information and bare contract metadata."""
    emitter = general_config.emitter
    ensure_config_root(config_root)
    initialize_deployer_interface(poa=poa,
                                  provider_uri=provider_uri,
                                  emitter=emitter,
                                  ignore_solidity_check=ignore_solidity_check)
    download_required = not bool(registry_infile)
    registry = establish_deployer_registry(emitter=emitter,
                                           registry_infile=registry_infile,
                                           download_registry=download_required,
                                           network=network if download_required else None)
    paint_deployer_contract_inspection(emitter=emitter,
                                       registry=registry,
                                       deployer_address=deployer_address)


@deploy.command()
@group_general_config
@group_actor_options
@option_target_address
@option_ignore_deployed
@option_confirmations
@click.option('--retarget', '-d', help="Retarget a contract's proxy.", is_flag=True)
@click.option('--multisig', help="Build raw transaction for upgrade via MultiSig ", is_flag=True)
def upgrade(general_config, actor_options, retarget, target_address, ignore_deployed, multisig, confirmations):
    """Upgrade NuCypher existing proxy contract deployments."""

    #
    # Setup
    #

    emitter = general_config.emitter
    ADMINISTRATOR, deployer_address, blockchain, local_registry = actor_options.create_actor(emitter, is_multisig=bool(multisig))  # FIXME: Workaround for building MultiSig TXs | NRN

    #
    # Pre-flight
    #

    contract_name = actor_options.contract_name
    if not contract_name:
        raise click.BadArgumentUsage(message="--contract-name is required when using --upgrade")

    try:
        # Check contract name exists
        Deployer = ADMINISTRATOR.deployers[contract_name]
    except KeyError:
        message = UNKNOWN_CONTRACT_NAME.format(contract_name=contract_name, constants=ADMINISTRATOR.deployers.keys())
        emitter.echo(message, color='red', bold=True)
        raise click.Abort()
    deployer = Deployer(registry=local_registry)

    # Check deployer address is owner
    if Deployer._ownable and deployer_address != deployer.owner:  # blockchain read
        emitter.echo(DEPLOYER_IS_NOT_OWNER.format(deployer_address=deployer_address,
                                                  contract_name=contract_name,
                                                  agent=deployer.make_agent()))
        raise click.Abort()
    else:
        emitter.echo('✓ Verified deployer address as contract owner', color='green')

    #
    # Business
    #

    if multisig:
        if not target_address:
            raise click.BadArgumentUsage(message="--multisig requires using --target-address.")
        if not actor_options.force:
            click.confirm(CONFIRM_BUILD_RETARGET_TRANSACTION.format(contract_name=contract_name,
                                                                    target_address=target_address), abort=True)
        transaction = ADMINISTRATOR.retarget_proxy(contract_name=contract_name,
                                                   target_address=target_address,
                                                   just_build_transaction=True,
                                                   confirmations=confirmations)

        trustee_address = select_client_account(emitter=emitter,
                                                prompt="Select trustee address",
                                                provider_uri=actor_options.provider_uri,
                                                show_eth_balance=False,
                                                show_nu_balance=False,
                                                show_staking=False)

        if not actor_options.force:
            click.confirm(CONFIRM_SELECTED_ACCOUNT.format(address=trustee_address), abort=True)

        trustee = Trustee(registry=local_registry, checksum_address=trustee_address)
        transaction_proposal = trustee.create_transaction_proposal(transaction)

        message = SUCCESSFUL_RETARGET_TX_BUILT.format(contract_name=contract_name, target_address=target_address)
        emitter.message(message, color='green')
        paint_multisig_proposed_transaction(emitter, transaction_proposal)  # TODO: Show decoded function too

        filepath = f'proposal-{trustee.multisig_agent.contract_address[:8]}-TX-{transaction_proposal.nonce}.json'
        transaction_proposal.write(filepath=filepath)
        emitter.echo(SUCCESSFUL_SAVE_MULTISIG_TX_PROPOSAL.format(filepath=filepath), color='blue', bold=True)
        return  # Exit

    elif retarget:
        if not target_address:
            raise click.BadArgumentUsage(message="--target-address is required when using --retarget")
        if not actor_options.force:
            click.confirm(CONFIRM_RETARGET.format(contract_name=contract_name, target_address=target_address), abort=True)
        receipt = ADMINISTRATOR.retarget_proxy(contract_name=contract_name,target_address=target_address, confirmations=confirmations)
        message = SUCCESSFUL_RETARGET.format(contract_name=contract_name, target_address=target_address)
        emitter.message(message, color='green')
        paint_receipt_summary(emitter=emitter, receipt=receipt)
        return  # Exit

    else:
        github_registry = establish_deployer_registry(emitter=emitter,
                                                      download_registry=True,
                                                      network=actor_options.network)
        if not actor_options.force:

            # Check for human verification of versioned upgrade details
            click.confirm(CONFIRM_BEGIN_UPGRADE.format(contract_name=contract_name), abort=True)
            if deployer._ownable:  # Only ownable + upgradeable contracts apply
                verify_upgrade_details(blockchain=blockchain,
                                       registry=github_registry,
                                       deployer=deployer)

        # Success
        receipts = ADMINISTRATOR.upgrade_contract(contract_name=contract_name,
                                                  ignore_deployed=ignore_deployed,
                                                  confirmations=confirmations)
        emitter.message(SUCCESSFUL_UPGRADE.format(contract_name=contract_name), color='green')

        for name, receipt in receipts.items():
            paint_receipt_summary(emitter=emitter, receipt=receipt)
        emitter.echo(REGISTRY_PUBLICATION_HINT.format(contract_name=contract_name,
                                                      local_registry=local_registry,
                                                      network=actor_options.network), color='blue')
        emitter.echo(ETHERSCAN_VERIFY_HINT.format(solc_version=SOLIDITY_COMPILER_VERSION), color='blue')
        return  # Exit


@deploy.command()
@group_general_config
@group_actor_options
def rollback(general_config, actor_options):
    """Rollback a proxy contract's target."""
    emitter = general_config.emitter
    ADMINISTRATOR, _, _, _ = actor_options.create_actor(emitter)
    if not actor_options.contract_name:
        raise click.BadArgumentUsage(message="--contract-name is required when using --rollback")
    receipt = ADMINISTRATOR.rollback_contract(contract_name=actor_options.contract_name)
    paint_receipt_summary(emitter=emitter, receipt=receipt)


@deploy.command()
@group_general_config
@group_actor_options
@option_gas
@option_ignore_deployed
@option_parameters
@option_confirmations
@click.option('--mode',
              help="Deploy a contract following all steps ('full'), up to idle status ('idle'), "
                   "just initialization step ('init', only for StakingEscrow) "
                   "or just the bare contract ('bare'). Defaults to 'full'",
              type=click.Choice(['full', 'idle', 'bare', 'init'], case_sensitive=False),
              default='full'
              )
@click.option('--activate', help="Activate a contract that is in idle mode", is_flag=True)
def contracts(general_config, actor_options, mode, activate, gas, ignore_deployed, confirmations, parameters):
    """Compile and deploy contracts."""

    emitter = general_config.emitter
    ADMINISTRATOR, _, deployer_interface, local_registry = actor_options.create_actor(emitter)
    chain_name = deployer_interface.client.chain_name

    deployment_parameters = {}
    if parameters:
        with open(parameters) as json_file:
            deployment_parameters = json.load(json_file)

    contract_name = actor_options.contract_name
    deployment_mode = constants.__getattr__(mode.upper())  # TODO: constant sorrow
    try:
        contract_deployer_class = ADMINISTRATOR.deployers[contract_name]
    except KeyError:
        message = UNKNOWN_CONTRACT_NAME.format(contract_name=contract_name, constants=ADMINISTRATOR.deployers.keys())
        emitter.echo(message, color='red', bold=True)
        raise click.Abort()

    if activate:
        # For the moment, only StakingEscrow can be activated
        staking_escrow_deployer = contract_deployer_class(registry=ADMINISTRATOR.registry)
        if contract_name != STAKING_ESCROW_CONTRACT_NAME or not staking_escrow_deployer.ready_to_activate:
            raise click.BadOptionUsage(option_name="--activate",
                                       message=f"You can only activate an idle instance of {STAKING_ESCROW_CONTRACT_NAME}")

        escrow_address = staking_escrow_deployer._get_deployed_contract().address
        prompt = CONFIRM_NETWORK_ACTIVATION.format(staking_escrow_name=STAKING_ESCROW_CONTRACT_NAME,
                                                   staking_escrow_address=escrow_address)
        click.confirm(prompt, abort=True)

        receipts = staking_escrow_deployer.activate(transacting_power=ADMINISTRATOR.transacting_power,
                                                    gas_limit=gas,
                                                    confirmations=confirmations)
        for tx_name, receipt in receipts.items():
            paint_receipt_summary(emitter=emitter,
                                  receipt=receipt,
                                  chain_name=chain_name,
                                  transaction_type=tx_name)
        return  # Exit

    # Stage Deployment
    paint_staged_deployment(deployer_interface=deployer_interface, administrator=ADMINISTRATOR, emitter=emitter)

    # Confirm Trigger Deployment
    if not confirm_deployment(emitter=emitter, deployer_interface=deployer_interface):
        raise click.Abort()

    # Deploy
    emitter.echo(CONTRACT_DEPLOYMENT_SERIES_BEGIN_ADVISORY.format(contract_name=contract_name))
    receipts, agent = ADMINISTRATOR.deploy_contract(contract_name=contract_name,
                                                    gas_limit=gas,
                                                    deployment_mode=deployment_mode,
                                                    ignore_deployed=ignore_deployed,
                                                    confirmations=confirmations,
                                                    deployment_parameters=deployment_parameters)

    # Report
    paint_contract_deployment(contract_name=contract_name,
                              contract_address=agent.contract_address,
                              receipts=receipts,
                              emitter=emitter,
                              chain_name=chain_name,
                              open_in_browser=actor_options.etherscan)

    # Success
    registry_outfile = local_registry.filepath
    emitter.echo(SUCCESSFUL_REGISTRY_CREATION.format(registry_outfile=registry_outfile), bold=True, color='blue')

    # TODO: Reintroduce?
    # Save transaction metadata
    # receipts_filepath = ADMINISTRATOR.save_deployment_receipts(receipts=receipts)
    # emitter.echo(SUCCESSFUL_SAVE_DEPLOY_RECEIPTS.format(receipts_filepath=receipts_filepath), color='blue', bold=True)


@deploy.command("transfer-ownership")
@group_general_config
@group_actor_options
@option_target_address
@option_gas
def transfer_ownership(general_config, actor_options, target_address, gas):
    """Transfer ownership of contracts to another address."""
    emitter = general_config.emitter
    ADMINISTRATOR, _, _, _ = actor_options.create_actor(emitter)

    if not target_address:
        target_address = click.prompt(PROMPT_NEW_OWNER_ADDRESS, type=EIP55_CHECKSUM_ADDRESS)

    contract_name = actor_options.contract_name
    if not contract_name:
        raise click.MissingParameter(param="--contract-name", message="You need to specify an ownable contract")

    try:
        contract_deployer_class = ADMINISTRATOR.deployers[contract_name]
    except KeyError:
        message = UNKNOWN_CONTRACT_NAME.format(contract_name=contract_name,
                                               contracts=ADMINISTRATOR.ownable_deployer_classes.keys())
        emitter.echo(message, color='red', bold=True)
        raise click.Abort()

    if contract_deployer_class not in ADMINISTRATOR.ownable_deployer_classes:
        message = CONTRACT_IS_NOT_OWNABLE.format(contract_name=contract_name)
        emitter.echo(message, color='red', bold=True)
        raise click.Abort()

    contract_deployer = contract_deployer_class(registry=ADMINISTRATOR.registry)
    receipt = contract_deployer.transfer_ownership(transacting_power=ADMINISTRATOR.transacting_power,
                                                   new_owner=target_address,
                                                   transaction_gas_limit=gas)
    paint_receipt_summary(emitter=emitter, receipt=receipt)


@deploy.command("set-range")
@group_general_config
@group_actor_options
@click.option('--minimum', help="Minimum value for range (in wei)", type=WEI)
@click.option('--default', help="Default value for range (in wei)", type=WEI)
@click.option('--maximum', help="Maximum value for range (in wei)", type=WEI)
def set_range(general_config, actor_options, minimum, default, maximum):
    """
    Set the minimum, default & maximum fee rate for all policies ('global fee range') in the policy manager contract.
    The minimum acceptable fee rate (set by stakers) must fall within the global fee range.
    """
    emitter = general_config.emitter
    ADMINISTRATOR, _, _, _ = actor_options.create_actor(emitter)

    if not minimum:
        minimum = click.prompt("Enter new minimum value for range", type=click.IntRange(min=0))
    if not default:
        default = click.prompt("Enter new default value for range", type=click.IntRange(min=minimum))
    if not maximum:
        maximum = click.prompt("Enter new maximum value for range", type=click.IntRange(min=default))

    ADMINISTRATOR.set_fee_rate_range(minimum=minimum, default=default, maximum=maximum)
    emitter.echo(MINIMUM_POLICY_RATE_EXCEEDED_WARNING.format(minimum=minimum, maximum=maximum, default=default))
