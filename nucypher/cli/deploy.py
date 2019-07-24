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
import time

import click
import maya

from nucypher.blockchain.eth.actors import DeployerActor
from nucypher.blockchain.eth.agents import NucypherTokenAgent
from nucypher.blockchain.eth.clients import NuCypherGethDevnetProcess
from nucypher.blockchain.eth.interfaces import BlockchainDeployerInterface
from nucypher.blockchain.eth.registry import EthereumContractRegistry
from nucypher.blockchain.eth.sol.compile import SolidityCompiler
from nucypher.characters.banners import NU_BANNER
from nucypher.cli import actions
from nucypher.characters.control.emitters import StdoutEmitter
from nucypher.cli.actions import get_password, select_client_account
from nucypher.cli.painting import paint_contract_deployment
from nucypher.cli.types import EIP55_CHECKSUM_ADDRESS, EXISTING_READABLE_FILE
from nucypher.config.constants import DEFAULT_CONFIG_ROOT


@click.command()
@click.argument('action')
@click.option('--force', is_flag=True)
@click.option('--poa', help="Inject POA middleware", is_flag=True)
@click.option('--provider-uri', help="Blockchain provider's URI", type=click.STRING)
@click.option('--geth', '-G', help="Run using the built-in geth node", is_flag=True)
@click.option('--sync/--no-sync', default=True)
@click.option('--hw-wallet/--no-hw-wallet', default=False)  # TODO: Make True by default.
@click.option('--enode', help="An ethereum bootnode enode address to start learning from", type=click.STRING)
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
           geth,
           enode,
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
           sync,
           hw_wallet,
           force,
           dev):
    """Manage contract and registry deployment"""

    ETH_NODE = None

    emitter = StdoutEmitter()

    #
    # Validate
    #

    # Ensure config root exists, because we need a default place to put output files.
    config_root = config_root or DEFAULT_CONFIG_ROOT
    if not os.path.exists(config_root):
        os.makedirs(config_root)

    #
    # Connect to Blockchain
    #

    if geth:
        # Spawn geth child process
        ETH_NODE = NuCypherGethDevnetProcess(config_root=config_root)
        ETH_NODE.ensure_account_exists(password=get_password(confirm=True))
        ETH_NODE.start()  # TODO: Graceful shutdown
        provider_uri = ETH_NODE.provider_uri

    # Establish a contract registry from disk if specified
    registry_filepath = registry_outfile or registry_infile

    if dev:
        # TODO: Need a way to detect a geth--dev registry filepath here. (then deprecate the --dev flag)
        registry_filepath = os.path.join(DEFAULT_CONFIG_ROOT, 'dev_contract_registry.json')

    # Deployment-tuned blockchain connection
    blockchain = BlockchainDeployerInterface(provider_uri=provider_uri,
                                             poa=poa,
                                             compiler=SolidityCompiler(),
                                             registry=EthereumContractRegistry(registry_filepath=registry_filepath))

    try:
        blockchain.connect(fetch_registry=False, sync_now=sync)
    except BlockchainDeployerInterface.ConnectionFailed as e:
        emitter.echo(str(e), color='red', bold=True)
        raise click.Abort()

    #
    # Deployment Actor
    #

    if not deployer_address:
        deployer_address = select_client_account(emitter=emitter, blockchain=blockchain)

    # Verify Address
    if not force:
        click.confirm("Selected {} - Continue?".format(deployer_address), abort=True)

    password = None
    if not hw_wallet and not blockchain.client.is_local:
        password = get_password(confirm=False)

    deployer = DeployerActor(blockchain=blockchain,
                             client_password=password,
                             deployer_address=deployer_address)

    # Verify ETH Balance
    emitter.echo(f"\n\nDeployer ETH balance: {deployer.eth_balance}")
    if deployer.eth_balance == 0:
        emitter.echo("Deployer address has no ETH.", color='red', bold=True)
        raise click.Abort()

    # Add ETH Bootnode or Peer
    if enode:
        blockchain.client.add_peer(enode)
        emitter.echo(f"Added ethereum peer {enode}")

    #
    # Action switch
    #

    if action == 'upgrade':
        if not contract_name:
            raise click.BadArgumentUsage(message="--contract-name is required when using --upgrade")
        existing_secret = click.prompt('Enter existing contract upgrade secret', hide_input=True)
        new_secret = click.prompt('Enter new contract upgrade secret', hide_input=True, confirmation_prompt=True)
        deployer.upgrade_contract(contract_name=contract_name,
                                  existing_plaintext_secret=existing_secret,
                                  new_plaintext_secret=new_secret)

    elif action == 'rollback':
        existing_secret = click.prompt('Enter existing contract upgrade secret', hide_input=True)
        new_secret = click.prompt('Enter new contract upgrade secret', hide_input=True, confirmation_prompt=True)
        deployer.rollback_contract(contract_name=contract_name,
                                   existing_plaintext_secret=existing_secret,
                                   new_plaintext_secret=new_secret)

    elif action == "contracts":

        #
        # Deploy Single Contract
        #

        if contract_name:
            try:
                contract_deployer = deployer.deployers[contract_name]
            except KeyError:
                message = f"No such contract {contract_name}. Available contracts are {deployer.deployers.keys()}"
                emitter.echo(message, color='red', bold=True)
                raise click.Abort()
            else:
                emitter.echo(f"Deploying {contract_name}")
                if contract_deployer._upgradeable:
                    secret = deployer.collect_deployment_secret(deployer=contract_deployer)
                    receipts, agent = deployer.deploy_contract(contract_name=contract_name, plaintext_secret=secret)
                else:
                    receipts, agent = deployer.deploy_contract(contract_name=contract_name, gas_limit=gas)
                paint_contract_deployment(contract_name=contract_name,
                                          contract_address=agent.contract_address,
                                          receipts=receipts,
                                          emitter=emitter)
            if ETH_NODE:
                ETH_NODE.stop()
            return

        registry_filepath = deployer.blockchain.registry.filepath
        if os.path.isfile(registry_filepath):
            emitter.echo(f"\nThere is an existing contract registry at {registry_filepath}.\n"
                         f"Did you mean 'nucypher-deploy upgrade'?\n", color='yellow')
            click.confirm("Optionally, destroy existing local registry and continue?", abort=True)
            click.confirm(f"Confirm deletion of contract registry '{registry_filepath}'?", abort=True)
            os.remove(registry_filepath)

        #
        # Stage Deployment
        #
        secrets = deployer.collect_deployment_secrets()

        emitter.clear()
        emitter.banner(NU_BANNER)

        emitter.echo(f"Current Time ........ {maya.now().iso8601()}")
        emitter.echo(f"Web3 Provider ....... {deployer.blockchain.provider_uri}")
        emitter.echo(f"Block ............... {deployer.blockchain.client.block_number}")
        emitter.echo(f"Gas Price ........... {deployer.blockchain.client.gas_price}")

        emitter.echo(f"Deployer Address .... {deployer.checksum_address}")
        emitter.echo(f"ETH ................. {deployer.eth_balance}")
        emitter.echo(f"Chain ID ............ {deployer.blockchain.client.chain_id}")
        emitter.echo(f"Chain Name .......... {deployer.blockchain.client.chain_name}")

        # Ask - Last chance to gracefully abort. This step cannot be forced.
        emitter.echo("\nDeployment successfully staged. Take a deep breath. \n", color='green')
        # Trigger Deployment
        if not actions.confirm_deployment(emitter=emitter, deployer=deployer):
            raise click.Abort()

        # Delay - Last chance to crash and abort
        emitter.echo(f"Starting deployment in 3 seconds...", color='red')
        time.sleep(1)
        emitter.echo(f"2...", color='yellow')
        time.sleep(1)
        emitter.echo(f"1...", color='green')
        time.sleep(1)
        emitter.echo(f"Deploying...", bold=True)

        #
        # DEPLOY
        #
        deployment_receipts = deployer.deploy_network_contracts(secrets=secrets, emitter=emitter)

        #
        # Success
        #

        # Paint outfile paths
        # TODO: Echo total gas used.
        # emitter.echo(f"Cumulative Gas Consumption: {total_gas_used} gas", bold=True, color='blue')

        registry_outfile = deployer.blockchain.registry.filepath
        emitter.echo('Generated registry {}'.format(registry_outfile), bold=True, color='blue')

        # Save transaction metadata
        receipts_filepath = deployer.save_deployment_receipts(receipts=deployment_receipts)
        emitter.echo(f"Saved deployment receipts to {receipts_filepath}", color='blue', bold=True)

    elif action == "allocations":
        if not allocation_infile:
            allocation_infile = click.prompt("Enter allocation data filepath")
        click.confirm("Continue deploying and allocating?", abort=True)
        deployer.deploy_beneficiaries_from_file(allocation_data_filepath=allocation_infile,
                                                allocation_outfile=allocation_outfile)

    elif action == "transfer":
        token_agent = NucypherTokenAgent(blockchain=blockchain)
        click.confirm(f"Transfer {amount} from {token_agent.contract_address} to {recipient_address}?", abort=True)
        txhash = token_agent.transfer(amount=amount, sender_address=token_agent.contract_address, target_address=recipient_address)
        emitter.echo(f"OK | {txhash}")

    else:
        raise click.BadArgumentUsage(message=f"Unknown action '{action}'")

    if ETH_NODE:
        ETH_NODE.stop()
