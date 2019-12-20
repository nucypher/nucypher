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
import functools
import os

import click

from nucypher.blockchain.eth.actors import ContractAdministrator
from nucypher.blockchain.eth.agents import NucypherTokenAgent, ContractAgency
from nucypher.blockchain.eth.interfaces import BlockchainDeployerInterface, BlockchainInterfaceFactory
from nucypher.blockchain.eth.registry import (
    BaseContractRegistry,
    CanonicalRegistrySource,
    InMemoryContractRegistry,
    RegistrySourceManager,
    GithubRegistrySource,
)
from nucypher.blockchain.eth.token import NU
from nucypher.characters.control.emitters import StdoutEmitter
from nucypher.cli.actions import (
    get_client_password,
    select_client_account,
    confirm_deployment,
    establish_deployer_registry
)
from nucypher.cli.painting import (
    paint_staged_deployment,
    paint_deployment_delay,
    paint_contract_deployment,
    paint_deployer_contract_inspection,
    paint_receipt_summary)
from nucypher.cli.types import EIP55_CHECKSUM_ADDRESS, EXISTING_READABLE_FILE
from nucypher.config.constants import DEFAULT_CONFIG_ROOT


# Args (provider_uri, contract_name, config_root, poa, force, etherscan, hw_wallet, deployer_address,
#       registry_infile, registry_outfile, dev)
def _admin_actor_options(func):
    @click.option('--provider', 'provider_uri', help="Blockchain provider's URI", type=click.STRING, required=True)
    @click.option('--contract-name', help="Deploy a single contract by name", type=click.STRING)
    @click.option('--config-root', help="Custom configuration directory", type=click.Path())
    @click.option('--poa', help="Inject POA middleware", is_flag=True)
    @click.option('--force', is_flag=True)
    @click.option('--etherscan/--no-etherscan', help="Enable/disable viewing TX in Etherscan", default=False)
    @click.option('--hw-wallet/--no-hw-wallet', default=False)  # TODO: Make True by default.
    @click.option('--deployer-address', help="Deployer's checksum address", type=EIP55_CHECKSUM_ADDRESS)
    @click.option('--registry-infile', help="Input path for contract registry file", type=EXISTING_READABLE_FILE)
    @click.option('--registry-outfile', help="Output path for contract registry file", type=click.Path(file_okay=True))
    @click.option('--dev', '-d', help="Forcibly use the development registry filepath.", is_flag=True)
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        return func(*args, **kwargs)
    return wrapper


@click.group()
def deploy():
    """
    Manage contract and registry deployment.
    """
    pass


@deploy.command(name='download-registry')
@click.option('--config-root', help="Custom configuration directory", type=click.Path())
@click.option('--registry-outfile', help="Output path for contract registry file", type=click.Path(file_okay=True))
@click.option('--network', help="", type=click.Choice(CanonicalRegistrySource.networks), default='goerli')  # TODO: #1496
@click.option('--force', is_flag=True)
def download_registry(config_root, registry_outfile, network, force):
    """
    Download the latest registry.
    """
    # Init
    emitter = StdoutEmitter()
    _ensure_config_root(config_root)

    github_source = GithubRegistrySource(network=network, registry_name=BaseContractRegistry.REGISTRY_NAME)
    source_manager = RegistrySourceManager(sources=[github_source])

    if not force:
        prompt = f"Fetch and download latest contract registry from {github_source}?"
        click.confirm(prompt, abort=True)
    try:
        registry = InMemoryContractRegistry.from_latest_publication(source_manager=source_manager)
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
@click.option('--provider', 'provider_uri', help="Blockchain provider's URI", type=click.STRING, required=True)
@click.option('--config-root', help="Custom configuration directory", type=click.Path())
@click.option('--registry-infile', help="Input path for contract registry file", type=EXISTING_READABLE_FILE)
@click.option('--deployer-address', help="Deployer's checksum address", type=EIP55_CHECKSUM_ADDRESS)
@click.option('--poa', help="Inject POA middleware", is_flag=True)
def inspect(provider_uri, config_root, registry_infile, deployer_address, poa):
    """
    Echo owner information and bare contract metadata.
    """
    # Init
    emitter = StdoutEmitter()
    _ensure_config_root(config_root)
    _initialize_blockchain(poa, provider_uri)

    local_registry = establish_deployer_registry(emitter=emitter,
                                                 registry_infile=registry_infile,
                                                 download_registry=not bool(registry_infile))
    paint_deployer_contract_inspection(emitter=emitter,
                                       registry=local_registry,
                                       deployer_address=deployer_address)


@deploy.command()
@_admin_actor_options
@click.option('--retarget', '-d', help="Retarget a contract's proxy.", is_flag=True)
@click.option('--target-address', help="Address of the target contract", type=EIP55_CHECKSUM_ADDRESS)
def upgrade(# Admin Actor Options
            provider_uri, contract_name, config_root, poa, force, etherscan, hw_wallet, deployer_address,
            registry_infile, registry_outfile, dev,

            # Other
            retarget, target_address):
    """
    Upgrade NuCypher existing proxy contract deployments.
    """
    # Init
    emitter = StdoutEmitter()
    _ensure_config_root(config_root)
    deployer_interface = _initialize_blockchain(poa, provider_uri)

    # Warnings
    _pre_launch_warnings(emitter, etherscan, hw_wallet)

    #
    # Make Authenticated Deployment Actor
    #
    ADMINISTRATOR, deployer_address, local_registry = _make_authenticated_deployment_actor(emitter,
                                                                                           provider_uri,
                                                                                           deployer_address,
                                                                                           deployer_interface,
                                                                                           contract_name,
                                                                                           registry_infile,
                                                                                           registry_outfile,
                                                                                           hw_wallet,
                                                                                           dev,
                                                                                           force)

    if not contract_name:
        raise click.BadArgumentUsage(message="--contract-name is required when using --upgrade")

    existing_secret = click.prompt('Enter existing contract upgrade secret', hide_input=True)
    new_secret = click.prompt('Enter new contract upgrade secret', hide_input=True, confirmation_prompt=True)

    if retarget:
        if not target_address:
            raise click.BadArgumentUsage(message="--target-address is required when using --retarget")
        if not force:
            click.confirm(f"Confirm re-target {contract_name}'s proxy to {target_address}?", abort=True)
        receipt = ADMINISTRATOR.retarget_proxy(contract_name=contract_name,
                                               target_address=target_address,
                                               existing_plaintext_secret=existing_secret,
                                               new_plaintext_secret=new_secret)
        emitter.message(f"Successfully re-targeted {contract_name} proxy to {target_address}", color='green')
        paint_receipt_summary(emitter=emitter, receipt=receipt)
    else:
        if not force:
            click.confirm(f"Confirm deploy new version of {contract_name} and retarget proxy?", abort=True)
        receipts = ADMINISTRATOR.upgrade_contract(contract_name=contract_name,
                                                  existing_plaintext_secret=existing_secret,
                                                  new_plaintext_secret=new_secret)
        emitter.message(f"Successfully deployed and upgraded {contract_name}", color='green')
        for name, receipt in receipts.items():
            paint_receipt_summary(emitter=emitter, receipt=receipt)


@deploy.command()
@_admin_actor_options
def rollback(# Admin Actor Options
             provider_uri, contract_name, config_root, poa, force, etherscan, hw_wallet, deployer_address,
             registry_infile, registry_outfile, dev):
    """
    Rollback a proxy contract's target.
    """
    # Init
    emitter = StdoutEmitter()
    _ensure_config_root(config_root)
    deployer_interface = _initialize_blockchain(poa, provider_uri)

    # Warnings
    _pre_launch_warnings(emitter, etherscan, hw_wallet)

    #
    # Make Authenticated Deployment Actor
    #
    ADMINISTRATOR, deployer_address, local_registry = _make_authenticated_deployment_actor(emitter,
                                                                                           provider_uri,
                                                                                           deployer_address,
                                                                                           deployer_interface,
                                                                                           contract_name,
                                                                                           registry_infile,
                                                                                           registry_outfile,
                                                                                           hw_wallet,
                                                                                           dev,
                                                                                           force)

    if not contract_name:
        raise click.BadArgumentUsage(message="--contract-name is required when using --rollback")
    existing_secret = click.prompt('Enter existing contract upgrade secret', hide_input=True)
    new_secret = click.prompt('Enter new contract upgrade secret', hide_input=True, confirmation_prompt=True)
    ADMINISTRATOR.rollback_contract(contract_name=contract_name,
                                    existing_plaintext_secret=existing_secret,
                                    new_plaintext_secret=new_secret)


@deploy.command()
@_admin_actor_options
@click.option('--bare', help="Deploy a contract *only* without any additional operations.", is_flag=True)
@click.option('--gas', help="Operate with a specified gas per-transaction limit", type=click.IntRange(min=1))
def contracts(# Admin Actor Options
              provider_uri, contract_name, config_root, poa, force, etherscan, hw_wallet, deployer_address,
              registry_infile, registry_outfile, dev,

              # Other
              bare, gas):
    """
    Compile and deploy contracts.
    """
    # Init
    emitter = StdoutEmitter()
    _ensure_config_root(config_root)
    deployer_interface = _initialize_blockchain(poa, provider_uri)

    # Warnings
    _pre_launch_warnings(emitter, etherscan, hw_wallet)

    #
    # Make Authenticated Deployment Actor
    #
    ADMINISTRATOR, deployer_address, local_registry = _make_authenticated_deployment_actor(emitter,
                                                                                           provider_uri,
                                                                                           deployer_address,
                                                                                           deployer_interface,
                                                                                           contract_name,
                                                                                           registry_infile,
                                                                                           registry_outfile,
                                                                                           hw_wallet,
                                                                                           dev,
                                                                                           force)

    #
    # Deploy Single Contract (Amend Registry)
    #

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
                                                            bare=bare)
        else:
            # Non-Upgradeable or Bare
            receipts, agent = ADMINISTRATOR.deploy_contract(contract_name=contract_name,
                                                            gas_limit=gas,
                                                            bare=bare)

        # Report
        paint_contract_deployment(contract_name=contract_name,
                                  contract_address=agent.contract_address,
                                  receipts=receipts,
                                  emitter=emitter,
                                  chain_name=deployer_interface.client.chain_name,
                                  open_in_browser=etherscan)
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
                                                                 interactive=not force,
                                                                 etherscan=etherscan)

    # Paint outfile paths
    registry_outfile = local_registry.filepath
    emitter.echo('Generated registry {}'.format(registry_outfile), bold=True, color='blue')

    # Save transaction metadata
    receipts_filepath = ADMINISTRATOR.save_deployment_receipts(receipts=deployment_receipts)
    emitter.echo(f"Saved deployment receipts to {receipts_filepath}", color='blue', bold=True)


@deploy.command()
@_admin_actor_options
@click.option('--allocation-infile', help="Input path for token allocation JSON file", type=EXISTING_READABLE_FILE)
@click.option('--allocation-outfile', help="Output path for token allocation JSON file",
              type=click.Path(exists=False, file_okay=True))
def allocations(# Admin Actor Options
                provider_uri, contract_name, config_root, poa, force, etherscan, hw_wallet, deployer_address,
                registry_infile, registry_outfile, dev,

                # Other
                allocation_infile, allocation_outfile):
    """
    Deploy pre-allocation contracts.
    """
    # Init
    emitter = StdoutEmitter()
    _ensure_config_root(config_root)
    deployer_interface = _initialize_blockchain(poa, provider_uri)

    # Warnings
    _pre_launch_warnings(emitter, etherscan, hw_wallet)

    #
    # Make Authenticated Deployment Actor
    #
    ADMINISTRATOR, deployer_address, local_registry = _make_authenticated_deployment_actor(emitter,
                                                                                           provider_uri,
                                                                                           deployer_address,
                                                                                           deployer_interface,
                                                                                           contract_name,
                                                                                           registry_infile,
                                                                                           registry_outfile,
                                                                                           hw_wallet,
                                                                                           dev,
                                                                                           force)

    if not allocation_infile:
        allocation_infile = click.prompt("Enter allocation data filepath")
    ADMINISTRATOR.deploy_beneficiaries_from_file(allocation_data_filepath=allocation_infile,
                                                 allocation_outfile=allocation_outfile,
                                                 emitter=emitter,
                                                 interactive=not force)


@deploy.command(name='transfer-tokens')
@_admin_actor_options
@click.option('--target-address', help="Recipient's checksum address for token or ownership transference.",
              type=EIP55_CHECKSUM_ADDRESS)
@click.option('--value', help="Amount of tokens to transfer in the smallest denomination", type=click.INT)
def transfer_tokens(# Admin Actor Options
                    provider_uri, contract_name, config_root, poa, force, etherscan, hw_wallet, deployer_address,
                    registry_infile, registry_outfile, dev,

                    # Other
                    target_address, value):
    """
    Transfer tokens from contract's owner address to another address
    """
    # Init
    emitter = StdoutEmitter()
    _ensure_config_root(config_root)
    deployer_interface = _initialize_blockchain(poa, provider_uri)

    # Warnings
    _pre_launch_warnings(emitter, etherscan, hw_wallet)

    #
    # Make Authenticated Deployment Actor
    #
    ADMINISTRATOR, deployer_address, local_registry = _make_authenticated_deployment_actor(emitter,
                                                                                           provider_uri,
                                                                                           deployer_address,
                                                                                           deployer_interface,
                                                                                           contract_name,
                                                                                           registry_infile,
                                                                                           registry_outfile,
                                                                                           hw_wallet,
                                                                                           dev,
                                                                                           force)

    token_agent = ContractAgency.get_agent(NucypherTokenAgent, registry=local_registry)
    if not target_address:
        target_address = click.prompt("Enter recipient's checksum address", type=EIP55_CHECKSUM_ADDRESS)
    if not value:
        stake_value_range = click.FloatRange(min=0, clamp=False)
        value = NU.from_tokens(click.prompt(f"Enter value in NU", type=stake_value_range))

    click.confirm(f"Transfer {value} from {deployer_address} to {target_address}?", abort=True)
    receipt = token_agent.transfer(amount=value,
                                   sender_address=deployer_address,
                                   target_address=target_address)
    emitter.echo(f"OK | Receipt: {receipt['transactionHash'].hex()}")


@deploy.command("transfer-ownership")
@_admin_actor_options
@click.option('--target-address', help="Recipient's checksum address for token or ownership transference.",
              type=EIP55_CHECKSUM_ADDRESS)
@click.option('--gas', help="Operate with a specified gas per-transaction limit", type=click.IntRange(min=1))
def transfer_ownership(# Admin Actor Options
                       provider_uri, contract_name, config_root, poa, force, etherscan, hw_wallet, deployer_address,
                       registry_infile, registry_outfile, dev,

                       # Other
                       target_address, gas):
    """
    Transfer ownership of contracts to another address.
    """
    # Init
    emitter = StdoutEmitter()
    _ensure_config_root(config_root)
    deployer_interface = _initialize_blockchain(poa, provider_uri)

    # Warnings
    _pre_launch_warnings(emitter, etherscan, hw_wallet)

    #
    # Make Authenticated Deployment Actor
    #
    ADMINISTRATOR, deployer_address, local_registry = _make_authenticated_deployment_actor(emitter,
                                                                                           provider_uri,
                                                                                           deployer_address,
                                                                                           deployer_interface,
                                                                                           contract_name,
                                                                                           registry_infile,
                                                                                           registry_outfile,
                                                                                           hw_wallet,
                                                                                           dev,
                                                                                           force)

    if not target_address:
        target_address = click.prompt("Enter new owner's checksum address", type=EIP55_CHECKSUM_ADDRESS)

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


def _make_authenticated_deployment_actor(emitter, provider_uri, deployer_address, deployer_interface, contract_name,
                                         registry_infile, registry_outfile, hw_wallet, dev, force):
    #
    # Establish Registry
    #
    local_registry = establish_deployer_registry(emitter=emitter,
                                                 use_existing_registry=bool(contract_name),
                                                 registry_infile=registry_infile,
                                                 registry_outfile=registry_outfile,
                                                 dev=dev)
    #
    # Make Authenticated Deployment Actor
    #
    # Verify Address & collect password
    if not deployer_address:
        prompt = "Select deployer account"
        deployer_address = select_client_account(emitter=emitter,
                                                 prompt=prompt,
                                                 provider_uri=provider_uri,
                                                 show_balances=False)
    if not force:
        click.confirm("Selected {} - Continue?".format(deployer_address), abort=True)
    password = None
    if not hw_wallet and not deployer_interface.client.is_local:
        password = get_client_password(checksum_address=deployer_address)
    # Produce Actor
    ADMINISTRATOR = ContractAdministrator(registry=local_registry,
                                          client_password=password,
                                          deployer_address=deployer_address)
    # Verify ETH Balance
    emitter.echo(f"\n\nDeployer ETH balance: {ADMINISTRATOR.eth_balance}")
    if ADMINISTRATOR.eth_balance == 0:
        emitter.echo("Deployer address has no ETH.", color='red', bold=True)
        raise click.Abort()
    return ADMINISTRATOR, deployer_address, local_registry


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


def _initialize_blockchain(poa, provider_uri):
    if not BlockchainInterfaceFactory.is_interface_initialized(provider_uri=provider_uri):
        # Note: For test compatibility.
        deployer_interface = BlockchainDeployerInterface(provider_uri=provider_uri, poa=poa)
        BlockchainInterfaceFactory.register_interface(interface=deployer_interface, sync=False,
                                                      show_sync_progress=False)
    else:
        deployer_interface = BlockchainInterfaceFactory.get_interface(provider_uri=provider_uri)

    deployer_interface.connect()
    return deployer_interface


def _ensure_config_root(config_root):
    # Ensure config root exists, because we need a default place to put output files.
    config_root = config_root or DEFAULT_CONFIG_ROOT
    if not os.path.exists(config_root):
        os.makedirs(config_root)