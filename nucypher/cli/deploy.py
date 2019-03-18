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

import click

from nucypher.blockchain.eth.actors import Deployer
from nucypher.blockchain.eth.agents import NucypherTokenAgent
from nucypher.blockchain.eth.chains import Blockchain
from nucypher.blockchain.eth.interfaces import BlockchainInterface
from nucypher.blockchain.eth.registry import EthereumContractRegistry
from nucypher.cli.config import nucypher_deployer_config
from nucypher.cli.types import EIP55_CHECKSUM_ADDRESS, EXISTING_READABLE_FILE
from nucypher.config.constants import DEFAULT_CONFIG_ROOT


@click.command()
@click.argument('action')
@click.option('--force', is_flag=True)
@click.option('--poa', help="Inject POA middleware", is_flag=True)
@click.option('--no-compile', help="Disables solidity contract compilation", is_flag=True)
@click.option('--provider-uri', help="Blockchain provider's URI", type=click.STRING)
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
           force):
    """Manage contract and registry deployment"""

    # Ensure config root exists, because we need a default place to put outfiles.
    config_root = config_root or DEFAULT_CONFIG_ROOT
    if not os.path.exists(config_root):
        os.makedirs(config_root)

    # Establish a contract Registry
    registry, registry_filepath = None, (registry_outfile or registry_infile)
    if registry_filepath is not None:
        registry = EthereumContractRegistry(registry_filepath=registry_filepath)

    # Connect to Blockchain
    blockchain = Blockchain.connect(provider_uri=provider_uri,
                                    registry=registry,
                                    deployer=True,
                                    compile=not no_compile,
                                    poa=poa)

    # OK - Let's init a Deployment actor
    if not deployer_address:
        etherbase = blockchain.interface.w3.eth.accounts[0]
        deployer_address = etherbase  # TODO: Make this required instead, perhaps interactive

    click.confirm("Deployer Address is {} - Continue?".format(deployer_address), abort=True)
    deployer = Deployer(blockchain=blockchain, deployer_address=deployer_address)

    # The Big Three
    if action == "contracts":
        secrets = click_config.collect_deployment_secrets()

        # Track tx hashes, and new agents
        __deployment_transactions = dict()
        __deployment_agents = dict()

        if force:
            deployer.blockchain.interface.registry._destroy()

        try:
            txhashes, agents = deployer.deploy_network_contracts(miner_secret=bytes(secrets.miner_secret, encoding='utf-8'),
                                                                 policy_secret=bytes(secrets.policy_secret, encoding='utf-8'))
        except BlockchainInterface.InterfaceError:
            raise  # TODO: Handle registry management here (contract may already exist)
        else:
            __deployment_transactions.update(txhashes)

        # User Escrow Proxy
        deployer.deploy_escrow_proxy(secret=bytes(secrets.escrow_proxy_secret, encoding='utf-8'))
        click.secho("Deployed!", fg='green', bold=True)

        #
        # Deploy Single Contract
        #
        if contract_name:

            try:
                deployer_func = deployer.deployers[contract_name]
            except KeyError:
                message = "No such contract {}. Available contracts are {}".format(contract_name, deployer.deployers.keys())
                click.secho(message, fg='red', bold=True)
                raise click.Abort()
            else:
                _txs, _agent = deployer_func()

        registry_outfile = deployer.blockchain.interface.registry.filepath
        click.secho('\nDeployment Transaction Hashes for {}'.format(registry_outfile), bold=True, fg='blue')
        for contract_name, transactions in __deployment_transactions.items():

            heading = '\n{} ({})'.format(contract_name, agents[contract_name].contract_address)
            click.secho(heading, bold=True)
            click.echo('*'*(42+3+len(contract_name)))

            total_gas_used = 0
            for tx_name, txhash in transactions.items():
                receipt = deployer.blockchain.wait_for_receipt(txhash=txhash)
                total_gas_used += int(receipt['gasUsed'])

                if receipt['status'] == 1:
                    click.secho("OK", fg='green', nl=False, bold=True)
                else:
                    click.secho("Failed", fg='red', nl=False, bold=True)
                click.secho(" | {}".format(tx_name), fg='yellow', nl=False)
                click.secho(" | {}".format(txhash.hex()), fg='yellow', nl=False)
                click.secho(" ({} gas)".format(receipt['cumulativeGasUsed']))

                click.secho("Block #{} | {}\n".format(receipt['blockNumber'], receipt['blockHash'].hex()))

        click.secho("Cumulative Gas Consumption: {} gas\n".format(total_gas_used), bold=True, fg='blue')

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
        return

    elif action == "destroy-registry":
        registry_filepath = deployer.blockchain.interface.registry.filepath
        click.confirm(f"Are you absolutely sure you want to destroy the contract registry at {registry_filepath}?", abort=True)
        os.remove(registry_filepath)
        click.secho(f"Successfully destroyed {registry_filepath}", fg='red')

    else:
        raise click.BadArgumentUsage
