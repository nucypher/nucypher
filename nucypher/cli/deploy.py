"""
This file is part of nucypher.

nucypher is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

nucypher is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with nucypher.  If not, see <https://www.gnu.org/licenses/>.
"""


import collections
import hashlib
import json

import click
from nucypher.cli.utilities import CHECKSUM_ADDRESS
from twisted.logger import Logger
from twisted.logger import globalLogPublisher
from typing import ClassVar, Tuple

from nucypher.blockchain.eth.agents import EthereumContractAgent
from nucypher.blockchain.eth.deployers import (
    NucypherTokenDeployer,
    MinerEscrowDeployer,
    PolicyManagerDeployer,
    ContractDeployer
)
from nucypher.cli.constants import BANNER
from nucypher.config.node import NodeConfiguration
from nucypher.utilities.logging import getTextFileObserver


#
# Click Eager Functions
#

def echo_version(ctx, param, value):
    if not value or ctx.resilient_parsing:
        return
    click.secho(BANNER, bold=True)
    ctx.exit()


#
# Deployers
#
DeployerInfo = collections.namedtuple('DeployerInfo', ('deployer_class',  # type: ContractDeployer
                                                       'upgradeable',     # type: bool
                                                       'agent_name',      # type: EthereumContractAgent
                                                       'dependant'))      # type: EthereumContractAgent


DEPLOYERS = collections.OrderedDict({

    NucypherTokenDeployer._contract_name: DeployerInfo(deployer_class=NucypherTokenDeployer,
                                                       upgradeable=False,
                                                       agent_name='token_agent',
                                                       dependant=None),

    MinerEscrowDeployer._contract_name: DeployerInfo(deployer_class=MinerEscrowDeployer,
                                                     upgradeable=True,
                                                     agent_name='miner_agent',
                                                     dependant='token_agent'),

    PolicyManagerDeployer._contract_name: DeployerInfo(deployer_class=PolicyManagerDeployer,
                                                       upgradeable=True,
                                                       agent_name='policy_agent',
                                                       dependant='miner_agent')
})


class NucypherDeployerClickConfig:

    log_to_file = True    # TODO: Use envvar

    def __init__(self):
        if self.log_to_file is True:
            globalLogPublisher.addObserver(getTextFileObserver())
        self.log = Logger(self.__class__.__name__)


# Register the above class as a decorator
uses_deployer_config = click.make_pass_decorator(NucypherDeployerClickConfig, ensure=True)


@click.command()
@click.argument('action')
@click.option('--contract-name',
              help="Deploy a single contract by name",
              type=click.STRING)
@click.option('--force', is_flag=True)
@click.option('--deployer-address',
              help="Deployer's checksum address",
              type=CHECKSUM_ADDRESS)
@click.option('--registry-outfile',
              help="Output path for new registry",
              type=click.Path(),
              default=NodeConfiguration.REGISTRY_SOURCE)
@uses_deployer_config
def deploy(config,
           action,
           deployer_address,
           contract_name,
           registry_outfile,
           force):
    """Manage contract and registry deployment"""

    if not config.deployer:
        click.secho("The --deployer flag must be used to issue the deploy command.", fg='red', bold=True)
        raise click.Abort()

    def __get_deployers():

        config.registry_filepath = registry_outfile
        config.connect_to_blockchain()
        config.blockchain.interface.deployer_address = deployer_address or config.accounts[0]
        click.confirm("Continue?", abort=True)
        return deployers

    if action == "contracts":
        deployers = __get_deployers()
        __deployment_transactions = dict()
        __deployment_agents = dict()

        available_deployers = ", ".join(deployers)
        click.echo("\n-----------------------------------------------")
        click.echo("Available Deployers: {}".format(available_deployers))
        click.echo("Blockchain Provider URI ... {}".format(config.blockchain.interface.provider_uri))
        click.echo("Registry Output Filepath .. {}".format(config.blockchain.interface.registry.filepath))
        click.echo("Deployer's Address ........ {}".format(config.blockchain.interface.deployer_address))
        click.echo("-----------------------------------------------\n")

        def __deploy_contract(deployer_class: ClassVar,
                              upgradeable: bool,
                              agent_name: str,
                              dependant: str = None
                              ) -> Tuple[dict, EthereumContractAgent]:

            __contract_name = deployer_class._contract_name

            __deployer_init_args = dict(blockchain=config.blockchain,
                                        deployer_address=config.blockchain.interface.deployer_address)

            if dependant is not None:
                __deployer_init_args.update({dependant: __deployment_agents[dependant]})

            if upgradeable:
                secret = click.prompt("Enter deployment secret for {}".format(__contract_name),
                                      hide_input=True, confirmation_prompt=True)
                secret_hash = hashlib.sha256(secret)
                __deployer_init_args.update({'secret_hash': secret_hash})

            __deployer = deployer_class(**__deployer_init_args)

            #
            # Arm
            #
            if not force:
                click.confirm("Arm {}?".format(deployer_class.__name__), abort=True)

            is_armed, disqualifications = __deployer.arm(abort=False)
            if not is_armed:
                disqualifications = ', '.join(disqualifications)
                click.secho("Failed to arm {}. Disqualifications: {}".format(__contract_name, disqualifications),
                            fg='red', bold=True)
                raise click.Abort()

            #
            # Deploy
            #
            if not force:
                click.confirm("Deploy {}?".format(__contract_name), abort=True)
            __transactions = __deployer.deploy()
            __deployment_transactions[__contract_name] = __transactions

            __agent = __deployer.make_agent()
            __deployment_agents[agent_name] = __agent

            click.secho("Deployed {} - Contract Address: {}".format(contract_name, __agent.contract_address),
                        fg='green', bold=True)

            return __transactions, __agent

        if contract_name:
            #
            # Deploy Single Contract
            #
            try:
                deployer_info = deployers[contract_name]
            except KeyError:
                click.secho(
                    "No such contract {}. Available contracts are {}".format(contract_name, available_deployers),
                    fg='red', bold=True)
                raise click.Abort()
            else:
                _txs, _agent = __deploy_contract(deployer_info.deployer_class,
                                                 upgradeable=deployer_info.upgradeable,
                                                 agent_name=deployer_info.agent_name,
                                                 dependant=deployer_info.dependant)
        else:
            #
            # Deploy All Contracts
            #
            for deployer_name, deployer_info in deployers.items():
                _txs, _agent = __deploy_contract(deployer_info.deployer_class,
                                                 upgradeable=deployer_info.upgradeable,
                                                 agent_name=deployer_info.agent_name,
                                                 dependant=deployer_info.dependant)

        if not force and click.prompt("View deployment transaction hashes?"):
            for contract_name, transactions in __deployment_transactions.items():
                click.echo(contract_name)
                for tx_name, txhash in transactions.items():
                    click.echo("{}:{}".format(tx_name, txhash))

        if not force and click.confirm("Save transaction hashes to JSON file?"):
            file = click.prompt("Enter output filepath", type=click.File(mode='w'))  # TODO: Save Txhashes
            file.__write(json.dumps(__deployment_transactions))
            click.secho("Successfully wrote transaction hashes file to {}".format(file.path), fg='green')

    else:
        raise click.BadArgumentUsage
