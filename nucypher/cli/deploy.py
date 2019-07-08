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
from constant_sorrow.constants import NO_STAKING_DEVICE

from nucypher.blockchain.eth.actors import Deployer
from nucypher.blockchain.eth.agents import NucypherTokenAgent
from nucypher.blockchain.eth.clients import NuCypherGethDevnetProcess
from nucypher.blockchain.eth.interfaces import BlockchainDeployerInterface
from nucypher.blockchain.eth.registry import EthereumContractRegistry
from nucypher.blockchain.eth.sol.compile import SolidityCompiler
from nucypher.characters.banners import NU_BANNER
from nucypher.cli.actions import get_password
from nucypher.cli.config import nucypher_deployer_config
from nucypher.cli.types import EIP55_CHECKSUM_ADDRESS, EXISTING_READABLE_FILE
from nucypher.config.constants import DEFAULT_CONFIG_ROOT


@click.command()
@click.argument('action')
@click.option('--force', is_flag=True)
@click.option('--poa', help="Inject POA middleware", is_flag=True)
@click.option('--no-compile', help="Disables solidity contract compilation", is_flag=True)
@click.option('--provider-uri', help="Blockchain provider's URI", type=click.STRING)
@click.option('--geth', '-G', help="Run using the built-in geth node", is_flag=True)
@click.option('--sync/--no-sync', default=True)
@click.option('--enode', help="An ethereum bootnode enode address to start learning from", type=click.STRING)
@click.option('--config-root', help="Custom configuration directory", type=click.Path())
@click.option('--contract-name', help="Deploy a single contract by name", type=click.STRING)
@click.option('--deployer-address', help="Deployer's checksum address", type=EIP55_CHECKSUM_ADDRESS)
@click.option('--recipient-address', help="Recipient's checksum address", type=EIP55_CHECKSUM_ADDRESS)
@click.option('--registry-infile', help="Input path for contract registry file", type=EXISTING_READABLE_FILE)
@click.option('--amount', help="Amount of tokens to transfer in the smallest denomination", type=click.INT)
@click.option('--registry-outfile', help="Output path for contract registry file", type=click.Path(file_okay=True))
@click.option('--allocation-infile', help="Input path for token allocation JSON file", type=EXISTING_READABLE_FILE)
@click.option('--allocation-outfile', help="Output path for token allocation JSON file", type=click.Path(exists=False, file_okay=True))
@nucypher_deployer_config
def deploy(click_config,
           action,
           poa,
           provider_uri,
           geth,
           enode,
           deployer_address,
           contract_name,
           allocation_infile,
           allocation_outfile,
           registry_infile,
           registry_outfile,
           no_compile,
           amount,
           recipient_address,
           config_root,
           sync,
           force):
    """Manage contract and registry deployment"""

    ETH_NODE = None

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
        ETH_NODE.ensure_account_exists(password=click_config.get_password(confirm=True))
        ETH_NODE.start()  # TODO: Graceful shutdown
        provider_uri = ETH_NODE.provider_uri

    # Establish a contract registry from disk if specified
    registry, registry_filepath = None, (registry_outfile or registry_infile)
    if registry_filepath is not None:
        registry = EthereumContractRegistry(registry_filepath=registry_filepath)

    # TODO: Move to Deployer with TransactingPower
    # Deployment-tuned blockchain connection
    blockchain = BlockchainDeployerInterface(provider_uri=provider_uri,
                                             poa=poa,
                                             registry=registry,
                                             compiler=SolidityCompiler())

    blockchain.connect(fetch_registry=False, sync_now=sync)

    #
    # Deployment Actor
    #

    if not deployer_address:
        for index, address in enumerate(blockchain.client.accounts):
            click.secho(f"{index} --- {address}")
        choices = click.IntRange(0, len(blockchain.client.accounts))
        deployer_address_index = click.prompt("Select deployer address", default=0, type=choices)
        deployer_address = blockchain.client.accounts[deployer_address_index]

    # Verify Address
    if not force:
        click.confirm("Selected {} - Continue?".format(deployer_address), abort=True)

    deployer = Deployer(blockchain=blockchain,
                        device=NO_STAKING_DEVICE,
                        client_password=get_password(confirm=False),
                        deployer_address=deployer_address)

    # Verify ETH Balance
    click.secho(f"\n\nDeployer ETH balance: {deployer.eth_balance}")
    if deployer.eth_balance == 0:
        click.secho("Deployer address has no ETH.", fg='red', bold=True)
        raise click.Abort()

    # Add ETH Bootnode or Peer
    if enode:
        if geth:
            blockchain.w3.geth.admin.addPeer(enode)
            click.secho(f"Added ethereum peer {enode}")
        else:
            raise NotImplemented  # TODO: other backends

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

        registry_filepath = deployer.blockchain.registry.filepath
        if os.path.isfile(registry_filepath):
            click.secho(f"\nThere is an existing contract registry at {registry_filepath}.\n"
                        f"Did you mean 'nucypher-deploy upgrade'?\n", fg='yellow')
            click.confirm("Optionally, destroy existing local registry and continue?", abort=True)
            click.confirm(f"Confirm deletion of contract registry '{registry_filepath}'?", abort=True)
            os.remove(registry_filepath)

        #
        # Deploy Single Contract
        #

        if contract_name:
            # TODO: Handle secret collection for single contract deployment

            try:
                deployer_func = deployer.deployers[contract_name]
            except KeyError:
                message = f"No such contract {contract_name}. Available contracts are {deployer.deployers.keys()}"
                click.secho(message, fg='red', bold=True)
                raise click.Abort()
            else:
                # Deploy single contract
                _txs, _agent = deployer_func()

            # TODO: Painting for single contract deployment
            if ETH_NODE:
                ETH_NODE.stop()
            return

        #
        # Stage Deployment
        #

        # Track tx hashes, and new agents
        __deployment_transactions = dict()
        __deployment_agents = dict()

        secrets = click_config.collect_deployment_secrets()
        click.clear()
        click.secho(NU_BANNER)

        w3 = deployer.blockchain.w3
        click.secho(f"Current Time ........ {maya.now().iso8601()}")
        click.secho(f"Web3 Provider ....... {deployer.blockchain.provider_uri}")
        click.secho(f"Block ............... {deployer.blockchain.client.block_number}")
        click.secho(f"Gas Price ........... {deployer.blockchain.client.gas_price}")

        click.secho(f"Deployer Address .... {deployer.checksum_address}")
        click.secho(f"ETH ................. {deployer.eth_balance}")
        click.secho(f"Chain ID ............ {deployer.blockchain.client.chain_id}")
        click.secho(f"Chain Name .......... {deployer.blockchain.client.chain_name}")

        # Ask - Last chance to gracefully abort
        if not force:
            click.secho("\nDeployment successfully staged. Take a deep breath. \n", fg='green')
            if click.prompt("Type 'DEPLOY' to continue") != 'DEPLOY':
                raise click.Abort()

        # Delay - Last chance to crash and abort
        click.secho(f"Starting deployment in 3 seconds...", fg='red')
        time.sleep(1)
        click.secho(f"2...", fg='yellow')
        time.sleep(1)
        click.secho(f"1...", fg='green')
        time.sleep(1)
        click.secho(f"Deploying...", bold=True)

        #
        # DEPLOY < -------
        #

        txhashes, deployers = deployer.deploy_network_contracts(staker_secret=secrets.staker_secret,
                                                                policy_secret=secrets.policy_secret,
                                                                adjudicator_secret=secrets.adjudicator_secret,
                                                                user_escrow_proxy_secret=secrets.escrow_proxy_secret)

        # Success
        __deployment_transactions.update(txhashes)

        #
        # Paint
        #

        total_gas_used = 0  # TODO: may be faulty
        for contract_name, transactions in __deployment_transactions.items():

            # Paint heading
            heading = '\n{} ({})'.format(contract_name, deployers[contract_name].contract_address)
            click.secho(heading, bold=True)
            click.echo('*'*(42+3+len(contract_name)))

            for tx_name, txhash in transactions.items():

                # Wait for inclusion in the blockchain
                receipt = deployer.blockchain.w3.eth.waitForTransactionReceipt(txhash)
                click.secho("OK", fg='green', nl=False, bold=True)

                # Accumulate gas
                total_gas_used += int(receipt['gasUsed'])

                # Paint
                click.secho(" | {}".format(tx_name), fg='yellow', nl=False)
                click.secho(" | {}".format(txhash.hex()), fg='yellow', nl=False)
                click.secho(" ({} gas)".format(receipt['cumulativeGasUsed']))
                click.secho("Block #{} | {}\n".format(receipt['blockNumber'], receipt['blockHash'].hex()))

        # Paint outfile paths
        click.secho("Cumulative Gas Consumption: {} gas".format(total_gas_used), bold=True, fg='blue')
        registry_outfile = deployer.blockchain.registry.filepath
        click.secho('Generated registry {}'.format(registry_outfile), bold=True, fg='blue')

        # Save transaction metadata
        receipts_filepath = deployer.save_deployment_receipts(transactions=__deployment_transactions)
        click.secho(f"Saved deployment receipts to {receipts_filepath}", fg='blue', bold=True)

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
        click.secho(f"OK | {txhash}")

    else:
        raise click.BadArgumentUsage(message=f"Unknown action '{action}'")

    if ETH_NODE:
        ETH_NODE.stop()
