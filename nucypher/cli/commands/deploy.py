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

import os

import click

from nucypher.blockchain.eth.actors import ContractAdministrator
from nucypher.blockchain.eth.agents import NucypherTokenAgent, ContractAgency
from nucypher.blockchain.eth.interfaces import BlockchainDeployerInterface, BlockchainInterfaceFactory
from nucypher.blockchain.eth.registry import (
    BaseContractRegistry,
    InMemoryContractRegistry,
    RegistrySourceManager,
    GithubRegistrySource
)
from nucypher.blockchain.eth.networks import NetworksInventory
from nucypher.blockchain.eth.token import NU
from nucypher.cli.actions import (
    get_client_password,
    select_client_account,
    confirm_deployment,
    establish_deployer_registry
)
from nucypher.cli.options import (
    group_options,
    option_config_root,
    option_etherscan,
    option_force,
    option_hw_wallet,
    option_poa,
    option_provider_uri,
)
from nucypher.cli.config import group_general_config
from nucypher.cli.painting import (
    paint_staged_deployment,
    paint_deployment_delay,
    paint_contract_deployment,
    paint_deployer_contract_inspection,
    paint_receipt_summary)
from nucypher.cli.types import EIP55_CHECKSUM_ADDRESS, EXISTING_READABLE_FILE
from nucypher.config.constants import DEFAULT_CONFIG_ROOT


option_deployer_address = click.option('--deployer-address', help="Deployer's checksum address", type=EIP55_CHECKSUM_ADDRESS)
option_registry_infile = click.option('--registry-infile', help="Input path for contract registry file", type=EXISTING_READABLE_FILE)
option_registry_outfile = click.option('--registry-outfile', help="Output path for contract registry file", type=click.Path(file_okay=True))
option_target_address = click.option('--target-address', help="Address of the target contract", type=EIP55_CHECKSUM_ADDRESS)
option_gas = click.option('--gas', help="Operate with a specified gas per-transaction limit", type=click.IntRange(min=1))
option_network = click.option('--network', help="Name of NuCypher network", type=click.Choice(NetworksInventory.networks))


def _pre_launch_warnings(emitter, etherscan, hw_wallet):
    if not hw_wallet:
        emitter.echo("WARNING: --no-hw-wallet is enabled.", color='yellow')
    if etherscan:
        emitter.echo("WARNING: --etherscan is enabled. "
                     "A browser tab will be opened with deployed contracts and TXs as provided by Etherscan.",
                     color='yellow')
    else:
        emitter.echo("WARNING: --etherscan is disabled. "
                     "If you want to see deployed contracts and TXs in your browser, activate --etherscan.",
                     color='yellow')


def _initialize_blockchain(poa, provider_uri, emitter):
    if not BlockchainInterfaceFactory.is_interface_initialized(provider_uri=provider_uri):
        # Note: For test compatibility.
        deployer_interface = BlockchainDeployerInterface(provider_uri=provider_uri, poa=poa)
        BlockchainInterfaceFactory.register_interface(interface=deployer_interface, sync=False,
                                                      emitter=emitter)
    else:
        deployer_interface = BlockchainInterfaceFactory.get_interface(provider_uri=provider_uri)

    deployer_interface.connect()
    return deployer_interface


def _ensure_config_root(config_root):
    # Ensure config root exists, because we need a default place to put output files.
    config_root = config_root or DEFAULT_CONFIG_ROOT
    if not os.path.exists(config_root):
        os.makedirs(config_root)


class ActorOptions:

    __option_name__ = 'actor_options'

    def __init__(self, provider_uri, deployer_address, contract_name,
                registry_infile, registry_outfile, hw_wallet, dev, force, poa, config_root, etherscan,
                se_test_mode):
        self.provider_uri = provider_uri
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
        self.se_test_mode = se_test_mode

    def create_actor(self, emitter):

        _ensure_config_root(self.config_root)
        deployer_interface = _initialize_blockchain(self.poa, self.provider_uri, emitter)

        # Warnings
        _pre_launch_warnings(emitter, self.etherscan, self.hw_wallet)

        #
        # Establish Registry
        #
        local_registry = establish_deployer_registry(emitter=emitter,
                                                     use_existing_registry=bool(self.contract_name),
                                                     registry_infile=self.registry_infile,
                                                     registry_outfile=self.registry_outfile,
                                                     dev=self.dev)
        #
        # Make Authenticated Deployment Actor
        #
        # Verify Address & collect password
        deployer_address = self.deployer_address
        if not deployer_address:
            prompt = "Select deployer account"
            deployer_address = select_client_account(emitter=emitter,
                                                     prompt=prompt,
                                                     provider_uri=self.provider_uri,
                                                     show_balances=False)

        if not self.force:
            click.confirm("Selected {} - Continue?".format(deployer_address), abort=True)

        password = None
        if not self.hw_wallet and not deployer_interface.client.is_local:
            password = get_client_password(checksum_address=deployer_address)
        # Produce Actor
        ADMINISTRATOR = ContractAdministrator(registry=local_registry,
                                              client_password=password,
                                              deployer_address=deployer_address,
                                              staking_escrow_test_mode=self.se_test_mode)
        # Verify ETH Balance
        emitter.echo(f"\n\nDeployer ETH balance: {ADMINISTRATOR.eth_balance}")
        if ADMINISTRATOR.eth_balance == 0:
            emitter.echo("Deployer address has no ETH.", color='red', bold=True)
            raise click.Abort()
        return ADMINISTRATOR, deployer_address, deployer_interface, local_registry


group_actor_options = group_options(
    ActorOptions,
    provider_uri=option_provider_uri(),
    contract_name=click.option('--contract-name', help="Deploy a single contract by name", type=click.STRING),
    poa=option_poa,
    force=option_force,
    hw_wallet=option_hw_wallet,
    deployer_address=option_deployer_address,
    registry_infile=option_registry_infile,
    registry_outfile=option_registry_outfile,
    dev=click.option('--dev', '-d', help="Forcibly use the development registry filepath.", is_flag=True),
    se_test_mode=click.option('--se-test-mode', help="Enable test mode for StakingEscrow in deployment.", is_flag=True),
    config_root=option_config_root,
    etherscan=option_etherscan,
    )


@click.group()
def deploy():
    """
    Manage contract and registry deployment.
    """
    pass


@deploy.command(name='download-registry')
@group_general_config
@option_config_root
@option_registry_outfile
@option_network
@option_force
def download_registry(general_config, config_root, registry_outfile, network, force):
    """
    Download the latest registry.
    """
    # Init
    emitter = general_config.emitter
    _ensure_config_root(config_root)

    github_source = GithubRegistrySource(network=network, registry_name=BaseContractRegistry.REGISTRY_NAME)
    source_manager = RegistrySourceManager(sources=[github_source])

    if not force:
        prompt = f"Fetch and download latest contract registry from {github_source}?"
        click.confirm(prompt, abort=True)
    try:
        registry = InMemoryContractRegistry.from_latest_publication(source_manager=source_manager, network=network)
    except RegistrySourceManager.NoSourcesAvailable:
        emitter.message("Registry not available.", color="red")
        raise click.Abort

    try:
        output_filepath = registry.commit(filepath=registry_outfile, overwrite=force)
    except InMemoryContractRegistry.CantOverwriteRegistry:
        emitter.message("Can't overwrite existing registry. Use '--force' to overwrite.", color="red")
        raise click.Abort
    emitter.message(f"Successfully downloaded latest registry to {output_filepath}")


@deploy.command()
@group_general_config
@option_provider_uri(required=True)
@option_config_root
@option_registry_infile
@option_deployer_address
@option_poa
def inspect(general_config, provider_uri, config_root, registry_infile, deployer_address, poa):
    """
    Echo owner information and bare contract metadata.
    """
    # Init
    emitter = general_config.emitter
    _ensure_config_root(config_root)
    _initialize_blockchain(poa, provider_uri, emitter)

    local_registry = establish_deployer_registry(emitter=emitter,
                                                 registry_infile=registry_infile,
                                                 download_registry=not bool(registry_infile))
    paint_deployer_contract_inspection(emitter=emitter,
                                       registry=local_registry,
                                       deployer_address=deployer_address)


@deploy.command()
@group_general_config
@group_actor_options
@click.option('--retarget', '-d', help="Retarget a contract's proxy.", is_flag=True)
@option_target_address
@click.option('--ignore-deployed', help="Ignore already deployed contracts if exist.", is_flag=True)
def upgrade(general_config, actor_options, retarget, target_address, ignore_deployed):
    """
    Upgrade NuCypher existing proxy contract deployments.
    """
    # Init
    emitter = general_config.emitter
    ADMINISTRATOR, _, _, _ = actor_options.create_actor(emitter)

    contract_name = actor_options.contract_name
    if not contract_name:
        raise click.BadArgumentUsage(message="--contract-name is required when using --upgrade")

    existing_secret = click.prompt('Enter existing contract upgrade secret', hide_input=True)
    new_secret = click.prompt('Enter new contract upgrade secret', hide_input=True, confirmation_prompt=True)

    if retarget:
        if not target_address:
            raise click.BadArgumentUsage(message="--target-address is required when using --retarget")
        if not actor_options.force:
            click.confirm(f"Confirm re-target {contract_name}'s proxy to {target_address}?", abort=True)
        receipt = ADMINISTRATOR.retarget_proxy(contract_name=contract_name,
                                               target_address=target_address,
                                               existing_plaintext_secret=existing_secret,
                                               new_plaintext_secret=new_secret)
        emitter.message(f"Successfully re-targeted {contract_name} proxy to {target_address}", color='green')
        paint_receipt_summary(emitter=emitter, receipt=receipt)
    else:
        if not actor_options.force:
            click.confirm(f"Confirm deploy new version of {contract_name} and retarget proxy?", abort=True)
        receipts = ADMINISTRATOR.upgrade_contract(contract_name=contract_name,
                                                  existing_plaintext_secret=existing_secret,
                                                  new_plaintext_secret=new_secret,
                                                  ignore_deployed=ignore_deployed)
        emitter.message(f"Successfully deployed and upgraded {contract_name}", color='green')
        for name, receipt in receipts.items():
            paint_receipt_summary(emitter=emitter, receipt=receipt)


@deploy.command()
@group_general_config
@group_actor_options
def rollback(general_config, actor_options):
    """
    Rollback a proxy contract's target.
    """
    emitter = general_config.emitter
    ADMINISTRATOR, _, _, _ = actor_options.create_actor(emitter)

    if not actor_options.contract_name:
        raise click.BadArgumentUsage(message="--contract-name is required when using --rollback")
    existing_secret = click.prompt('Enter existing contract upgrade secret', hide_input=True)
    new_secret = click.prompt('Enter new contract upgrade secret', hide_input=True, confirmation_prompt=True)
    ADMINISTRATOR.rollback_contract(contract_name=actor_options.contract_name,
                                    existing_plaintext_secret=existing_secret,
                                    new_plaintext_secret=new_secret)


@deploy.command()
@group_general_config
@group_actor_options
@click.option('--bare', help="Deploy a contract *only* without any additional operations.", is_flag=True)
@option_gas
@click.option('--ignore-deployed', help="Ignore already deployed contracts if exist.", is_flag=True)
def contracts(general_config, actor_options, bare, gas, ignore_deployed):
    """
    Compile and deploy contracts.
    """
    # Init

    emitter = general_config.emitter
    ADMINISTRATOR, _, deployer_interface, local_registry = actor_options.create_actor(emitter)

    #
    # Deploy Single Contract (Amend Registry)
    #
    contract_name = actor_options.contract_name
    if contract_name:
        try:
            contract_deployer = ADMINISTRATOR.deployers[contract_name]
        except KeyError:
            message = f"No such contract {contract_name}. Available contracts are {ADMINISTRATOR.deployers.keys()}"
            emitter.echo(message, color='red', bold=True)
            raise click.Abort()

        # Deploy
        emitter.echo(f"Deploying {contract_name}")
        if contract_deployer._upgradeable and not bare:
            # NOTE: Bare deployments do not engage the proxy contract
            secret = ADMINISTRATOR.collect_deployment_secret(deployer=contract_deployer)
            receipts, agent = ADMINISTRATOR.deploy_contract(contract_name=contract_name,
                                                            plaintext_secret=secret,
                                                            gas_limit=gas,
                                                            bare=bare,
                                                            ignore_deployed=ignore_deployed)
        else:
            # Non-Upgradeable or Bare
            receipts, agent = ADMINISTRATOR.deploy_contract(contract_name=contract_name,
                                                            gas_limit=gas,
                                                            bare=bare,
                                                            ignore_deployed=ignore_deployed)

        # Report
        paint_contract_deployment(contract_name=contract_name,
                                  contract_address=agent.contract_address,
                                  receipts=receipts,
                                  emitter=emitter,
                                  chain_name=deployer_interface.client.chain_name,
                                  open_in_browser=actor_options.etherscan)
        return  # Exit

    #
    # Deploy Automated Series (Create Registry)
    #

    # Confirm filesystem registry writes.
    if os.path.isfile(local_registry.filepath):
        emitter.echo(f"\nThere is an existing contract registry at {local_registry.filepath}.\n"
                     f"Did you mean 'nucypher-deploy upgrade'?\n", color='yellow')
        click.confirm("*DESTROY* existing local registry and continue?", abort=True)
        os.remove(local_registry.filepath)

    # Stage Deployment
    secrets = ADMINISTRATOR.collect_deployment_secrets()
    paint_staged_deployment(deployer_interface=deployer_interface, administrator=ADMINISTRATOR, emitter=emitter)

    # Confirm Trigger Deployment
    if not confirm_deployment(emitter=emitter, deployer_interface=deployer_interface):
        raise click.Abort()

    # Delay - Last chance to abort via KeyboardInterrupt
    paint_deployment_delay(emitter=emitter)

    # Execute Deployment
    deployment_receipts = ADMINISTRATOR.deploy_network_contracts(secrets=secrets,
                                                                 emitter=emitter,
                                                                 interactive=not actor_options.force,
                                                                 etherscan=actor_options.etherscan,
                                                                 ignore_deployed=ignore_deployed)

    # Paint outfile paths
    registry_outfile = local_registry.filepath
    emitter.echo('Generated registry {}'.format(registry_outfile), bold=True, color='blue')

    # Save transaction metadata
    receipts_filepath = ADMINISTRATOR.save_deployment_receipts(receipts=deployment_receipts)
    emitter.echo(f"Saved deployment receipts to {receipts_filepath}", color='blue', bold=True)


@deploy.command()
@group_general_config
@group_actor_options
@click.option('--allocation-infile', help="Input path for token allocation JSON file", type=EXISTING_READABLE_FILE)
@click.option('--allocation-outfile', help="Output path for token allocation JSON file",
              type=click.Path(exists=False, file_okay=True))
@click.option('--sidekick-account', help="A software-controlled account to assist the deployment",
              type=EIP55_CHECKSUM_ADDRESS)
def allocations(general_config, actor_options, allocation_infile, allocation_outfile, sidekick_account):
    """
    Deploy pre-allocation contracts.
    """
    emitter = general_config.emitter
    ADMINISTRATOR, _, deployer_interface, local_registry = actor_options.create_actor(emitter)

    if not sidekick_account and click.confirm('Do you want to use a sidekick account to assist during deployment?'):
        prompt = "Select sidekick account"
        sidekick_account = select_client_account(emitter=emitter,
                                                 prompt=prompt,
                                                 provider_uri=actor_options.provider_uri,
                                                 registry=local_registry,
                                                 show_balances=True)
        if not actor_options.force:
            click.confirm(f"Selected {sidekick_account} - Continue?", abort=True)

    if sidekick_account:
        password = None
        if not deployer_interface.client.is_local:
            password = get_client_password(checksum_address=sidekick_account)
        ADMINISTRATOR.recruit_sidekick(sidekick_address=sidekick_account, sidekick_password=password)

    if not allocation_infile:
        allocation_infile = click.prompt("Enter allocation data filepath")
    ADMINISTRATOR.deploy_beneficiaries_from_file(allocation_data_filepath=allocation_infile,
                                                 allocation_outfile=allocation_outfile,
                                                 emitter=emitter,
                                                 interactive=not actor_options.force)


@deploy.command(name='transfer-tokens')
@group_general_config
@group_actor_options
@option_target_address
@click.option('--value', help="Amount of tokens to transfer in the smallest denomination", type=click.INT)
def transfer_tokens(general_config, actor_options, target_address, value):
    """
    Transfer tokens from contract's owner address to another address
    """
    emitter = general_config.emitter
    ADMINISTRATOR, deployer_address, _, local_registry = actor_options.create_actor(emitter)

    token_agent = ContractAgency.get_agent(NucypherTokenAgent, registry=local_registry)
    if not target_address:
        target_address = click.prompt("Enter recipient's checksum address", type=EIP55_CHECKSUM_ADDRESS)
    if not value:
        stake_value_range = click.FloatRange(min=0, clamp=False)
        value = NU.from_tokens(click.prompt(f"Enter value in NU", type=stake_value_range))

    click.confirm(f"Transfer {value} from {deployer_address} to {target_address}?", abort=True)
    receipt = token_agent.transfer(amount=int(value), sender_address=deployer_address, target_address=target_address)
    paint_receipt_summary(emitter=emitter, receipt=receipt)


@deploy.command("transfer-ownership")
@group_general_config
@group_actor_options
@option_target_address
@option_gas
def transfer_ownership(general_config, actor_options, target_address, gas):
    """
    Transfer ownership of contracts to another address.
    """
    emitter = general_config.emitter
    ADMINISTRATOR, _, _, _ = actor_options.create_actor(emitter)

    if not target_address:
        target_address = click.prompt("Enter new owner's checksum address", type=EIP55_CHECKSUM_ADDRESS)

    contract_name = actor_options.contract_name
    if contract_name:
        try:
            contract_deployer_class = ADMINISTRATOR.deployers[contract_name]
        except KeyError:
            message = f"No such contract {contract_name}. Available contracts are {ADMINISTRATOR.deployers.keys()}"
            emitter.echo(message, color='red', bold=True)
            raise click.Abort()
        else:
            contract_deployer = contract_deployer_class(registry=ADMINISTRATOR.registry,
                                                        deployer_address=ADMINISTRATOR.deployer_address)
            receipt = contract_deployer.transfer_ownership(new_owner=target_address, transaction_gas_limit=gas)
            emitter.ipc(receipt, request_id=0, duration=0)  # TODO: #1216
    else:
        receipts = ADMINISTRATOR.relinquish_ownership(new_owner=target_address, transaction_gas_limit=gas)
        emitter.ipc(receipts, request_id=0, duration=0)  # TODO: #1216
