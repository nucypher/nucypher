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

from nucypher.blockchain.eth.actors import DeployerActor
from nucypher.blockchain.eth.agents import NucypherTokenAgent
from nucypher.blockchain.eth.interfaces import BlockchainDeployerInterface
from nucypher.blockchain.eth.registry import EthereumContractRegistry
from nucypher.characters.control.emitters import StdoutEmitter
from nucypher.cli import actions
from nucypher.cli.actions import get_nucypher_password
from nucypher.cli.actions import select_client_account
from nucypher.cli.painting import (
    paint_contract_deployment,
    paint_staged_deployment,
    paint_deployment_delay
)
from nucypher.cli.types import EIP55_CHECKSUM_ADDRESS, EXISTING_READABLE_FILE
from nucypher.config.constants import DEFAULT_CONFIG_ROOT


@click.command()
@click.argument('action')
@click.option('--force', is_flag=True)
@click.option('--poa', help="Inject POA middleware", is_flag=True)
@click.option('--provider', 'provider_uri', help="Blockchain provider's URI", type=click.STRING)
@click.option('--hw-wallet/--no-hw-wallet', default=False)  # TODO: Make True by default.
@click.option('--config-root', help="Custom configuration directory", type=click.Path())
@click.option('--contract-name', help="Deploy a single contract by name", type=click.STRING)
@click.option('--gas', help="Operate with a specified gas per-transaction limit", type=click.IntRange(min=1))
@click.option('--deployer-address', help="Deployer's checksum address", type=EIP55_CHECKSUM_ADDRESS)
@click.option('--recipient-address', help="Recipient's checksum address", type=EIP55_CHECKSUM_ADDRESS)
@click.option('--registry-infile', help="Input path for contract registry file", type=EXISTING_READABLE_FILE)
@click.option('--amount', help="Amount of tokens to transfer in the smallest denomination", type=click.INT)
@click.option('--dev', '-d', help="Forcibly use the development registry filepath.", is_flag=True)
@click.option('--registry-outfile', help="Output path for contract registry file", type=click.Path(file_okay=True))
@click.option('--allocation-infile', help="Input path for token allocation JSON file", type=EXISTING_READABLE_FILE)
@click.option('--allocation-outfile', help="Output path for token allocation JSON file", type=click.Path(exists=False, file_okay=True))
def deploy(action,
           poa,
           provider_uri,
           gas,
           deployer_address,
           contract_name,
           allocation_infile,
           allocation_outfile,
           registry_infile,
           registry_outfile,
           amount,
           recipient_address,
           config_root,
           hw_wallet,
           force,
           dev):
    """
    Manage contract and registry deployment.

    \b
    Actions
    -----------------------------------------------------------------------------
    contracts              Compile and deploy contracts.
    allocations            Deploy pre-allocation contracts.
    upgrade                Upgrade NuCypher existing proxy contract deployments.
    rollback               Rollback a proxy contract's target.
    status                 Echo owner information and bare contract metadata.
    transfer-tokens        Transfer tokens to another address.
    transfer-ownership     Transfer ownership of contracts to another address.
    """

    emitter = StdoutEmitter()

    #
    # Validate
    #

    # Ensure config root exists, because we need a default place to put output files.
    config_root = config_root or DEFAULT_CONFIG_ROOT
    if not os.path.exists(config_root):
        os.makedirs(config_root)

    #
    # Pre-Launch Warnings
    #

    if not hw_wallet:
        emitter.echo("WARNING: --no-hw-wallet is enabled.", color='yellow')

    #
    # Connect to Registry
    #

    # Establish a contract registry from disk if specified
    registry_filepath = registry_outfile or registry_infile
    if dev:
        # TODO: Need a way to detect a geth--dev registry filepath here. (then deprecate the --dev flag)
        registry_filepath = os.path.join(DEFAULT_CONFIG_ROOT, 'dev_contract_registry.json')
    registry = EthereumContractRegistry(registry_filepath=registry_filepath)
    emitter.echo(f"Using contract registry filepath {registry.filepath}")

    #
    # Connect to Blockchain
    #

    blockchain = BlockchainDeployerInterface(provider_uri=provider_uri, poa=poa, registry=registry)
    try:
        blockchain.connect(fetch_registry=False, sync_now=False)
    except BlockchainDeployerInterface.ConnectionFailed as e:
        emitter.echo(str(e), color='red', bold=True)
        raise click.Abort()

    #
    # Make Authenticated Deployment Actor
    #

    # Verify Address & collect password
    if not deployer_address:
        prompt = "Select deployer account"
        deployer_address = select_client_account(emitter=emitter, blockchain=blockchain, prompt=prompt)

    if not force:
        click.confirm("Selected {} - Continue?".format(deployer_address), abort=True)

    password = None
    if not hw_wallet and not blockchain.client.is_local:
        password = get_nucypher_password(confirm=False)

    # Produce Actor
    DEPLOYER = DeployerActor(blockchain=blockchain,
                             client_password=password,
                             deployer_address=deployer_address)

    # Verify ETH Balance
    emitter.echo(f"\n\nDeployer ETH balance: {DEPLOYER.eth_balance}")
    if DEPLOYER.eth_balance == 0:
        emitter.echo("Deployer address has no ETH.", color='red', bold=True)
        raise click.Abort()

    #
    # Action switch
    #

    if action == 'upgrade':
        if not contract_name:
            raise click.BadArgumentUsage(message="--contract-name is required when using --upgrade")
        existing_secret = click.prompt('Enter existing contract upgrade secret', hide_input=True)
        new_secret = click.prompt('Enter new contract upgrade secret', hide_input=True, confirmation_prompt=True)
        DEPLOYER.upgrade_contract(contract_name=contract_name,
                                  existing_plaintext_secret=existing_secret,
                                  new_plaintext_secret=new_secret)
        return  # Exit

    elif action == 'rollback':
        if not contract_name:
            raise click.BadArgumentUsage(message="--contract-name is required when using --rollback")
        existing_secret = click.prompt('Enter existing contract upgrade secret', hide_input=True)
        new_secret = click.prompt('Enter new contract upgrade secret', hide_input=True, confirmation_prompt=True)
        DEPLOYER.rollback_contract(contract_name=contract_name,
                                   existing_plaintext_secret=existing_secret,
                                   new_plaintext_secret=new_secret)
        return  # Exit

    elif action == "contracts":

        #
        # Deploy Single Contract (Amend Registry)
        #

        if contract_name:
            try:
                contract_deployer = DEPLOYER.deployers[contract_name]
            except KeyError:
                message = f"No such contract {contract_name}. Available contracts are {DEPLOYER.deployers.keys()}"
                emitter.echo(message, color='red', bold=True)
                raise click.Abort()
            else:
                emitter.echo(f"Deploying {contract_name}")
                if contract_deployer._upgradeable:
                    secret = DEPLOYER.collect_deployment_secret(deployer=contract_deployer)
                    receipts, agent = DEPLOYER.deploy_contract(contract_name=contract_name, plaintext_secret=secret)
                else:
                    receipts, agent = DEPLOYER.deploy_contract(contract_name=contract_name, gas_limit=gas)
                paint_contract_deployment(contract_name=contract_name,
                                          contract_address=agent.contract_address,
                                          receipts=receipts,
                                          emitter=emitter)
            return  # Exit

        #
        # Deploy Automated Series (Create Registry)
        #

        # Confirm filesystem registry writes.
        registry_filepath = DEPLOYER.blockchain.registry.filepath
        if os.path.isfile(registry_filepath):
            emitter.echo(f"\nThere is an existing contract registry at {registry_filepath}.\n"
                         f"Did you mean 'nucypher-deploy upgrade'?\n", color='yellow')
            click.confirm("*DESTROY* existing local registry and continue?", abort=True)
            os.remove(registry_filepath)

        # Stage Deployment
        secrets = DEPLOYER.collect_deployment_secrets()
        paint_staged_deployment(deployer=DEPLOYER, emitter=emitter)

        # Confirm Trigger Deployment
        if not actions.confirm_deployment(emitter=emitter, deployer=DEPLOYER):
            raise click.Abort()

        # Delay - Last chance to abort via KeyboardInterrupt
        paint_deployment_delay(emitter=emitter)

        # Execute Deployment
        deployment_receipts = DEPLOYER.deploy_network_contracts(secrets=secrets,
                                                                emitter=emitter,
                                                                interactive=not force)

        # Paint outfile paths
        registry_outfile = DEPLOYER.blockchain.registry.filepath
        emitter.echo('Generated registry {}'.format(registry_outfile), bold=True, color='blue')

        # Save transaction metadata
        receipts_filepath = DEPLOYER.save_deployment_receipts(receipts=deployment_receipts)
        emitter.echo(f"Saved deployment receipts to {receipts_filepath}", color='blue', bold=True)
        return  # Exit

    elif action == "allocations":
        if not allocation_infile:
            allocation_infile = click.prompt("Enter allocation data filepath")
        click.confirm("Continue deploying and allocating?", abort=True)
        DEPLOYER.deploy_beneficiaries_from_file(allocation_data_filepath=allocation_infile,
                                                allocation_outfile=allocation_outfile)
        return  # Exit

    elif action == "transfer":
        token_agent = NucypherTokenAgent(blockchain=blockchain)
        missing_options = list()
        if recipient_address is None:
            missing_options.append("--recipient-address")
        if amount is None:
            missing_options.append("--amount")
        if missing_options:
            raise click.BadOptionUsage(f"Need {' and '.join(missing_options)} to transfer tokens.")

        click.confirm(f"Transfer {amount} from {deployer_address} to {recipient_address}?", abort=True)
        receipt = token_agent.transfer(amount=amount, sender_address=deployer_address, target_address=recipient_address)
        emitter.echo(f"OK | Receipt: {receipt['transactionHash'].hex()}")
        return  # Exit

    else:
        raise click.BadArgumentUsage(message=f"Unknown action '{action}'")
