"""
NuCypher CLI
"""


# Set Default Curve #
#####################

from umbral.config import set_default_curve
set_default_curve()

#####################

import os
import click
from twisted.internet import reactor

from nucypher.blockchain.eth.agents import MinerAgent, PolicyAgent, NucypherTokenAgent
from tests.utilities.blockchain import bootstrap_fake_network
from nucypher.config.utils import parse_nucypher_ini_config, validate_nucypher_ini_config
from tests.utilities.simulate import SimulatedUrsulaProcessProtocol, UrsulaProcessProtocol

__version__ = '0.1.0-mock'  # TODO

DEFAULT_CONF_FILEPATH = '.'


class NucypherClickConfig:

    def __init__(self):

        self.verbose = True
        self.config_filepath = './.nucypher.ini'
        self.simulation_running = False

        # Connect to blockchain
        if not os.path.isfile(self.config_filepath):
            raise RuntimeError("No such config file {}".format(self.config_filepath))

        self.payload = parse_nucypher_ini_config(filepath=self.config_filepath)
        self.blockchain = self.payload['blockchain']

        # Three agents
        self.token_agent = NucypherTokenAgent(blockchain=self.blockchain)
        self.miner_agent = MinerAgent(token_agent=self.token_agent)
        self.policy_agent = PolicyAgent(miner_agent=self.miner_agent)

        self.accounts = self.blockchain.interface.w3.eth.accounts

        if self.payload['tester'] and self.payload['deploy']:
            self.blockchain.interface.deployer_address = self.accounts[0]

    @property
    def provider_uri(self):
        payload = self.payload['blockchain.provider']
        type, path = payload['type'], payload['path']
        uri_template = "{}://{}"
        return uri_template.format(type, path)

    @property
    def rest_uri(self):
        payload = self.payload['ursula.network.rest']
        host, port = payload['host'], payload['port']
        uri_template = "https://{}:{}"
        return uri_template.format(host, port)


uses_config = click.make_pass_decorator(NucypherClickConfig, ensure=True)


@click.group()
@click.option('--version', help="Prints the installed version.", is_flag=True)
@click.option('--verbose', help="Enable verbose mode.", is_flag=True)
@click.option('--config-file', help="Specify a custom config filepath.", type=click.Path())
@uses_config
def cli(config, verbose, version, config_file):
    """Configure and manage a nucypher nodes"""

    click.echo('''\n
                                  _               
                                 | |              
     _ __  _   _  ___ _   _ _ __ | |__   ___ _ __ 
    | '_ \| | | |/ __| | | | '_ \| '_ \ / _ \ '__|
    | | | | |_| | (__| |_| | |_) | | | |  __/ |   
    |_| |_|\__,_|\___|\__, | .__/|_| |_|\___|_|   
                       __/ | |                    
                      |___/|_|      
                                    
    version {}
    
    \n'''.format(__version__))

    # Store config data
    config.verbose = verbose
    config.config_filepath = config_file

    if config.verbose:
        click.echo("Running in verbose mode...")
    if version:
        click.echo("Version {}".format(__version__))


@cli.command()
@click.argument('action')
@click.option('--config-file', help="Specify a custom .ini configuration filepath")
@uses_config
def config(config, action, config_file):
    """Manage the nucypher .ini configuration file"""

    if action == "validate":
        validate_nucypher_ini_config(config_file)


@cli.command()
@click.argument('action', default='list', required=False)
@uses_config
def accounts(config, action):
    """Manage ethereum node accounts"""

    if action == 'list':
        for index, address in enumerate(config.accounts):
            if index == 0:
                row = 'etherbase | {}'.format(address)
            else:
                row = '{} ....... | {}'.format(index, address)
            click.echo(row)


@cli.command()
@click.argument('action', default='list', required=False)
@click.argument('ethereum_address', required=False)
@click.option('--stake-index', help="auto-stake a random amount and lock time", is_flag=True)
@uses_config
def stake(config, action, ethereum_address, stake_index):
    """Manage active node stakes on the blockchain"""

    if action == 'list':
        live_stakes = config.miner_agent.get_all_stakes(miner_address=ethereum_address)
        for index, stake_info in enumerate(live_stakes):
            row = '{} | {}'.format(index, stake_info)
            click.echo(row)

    elif action == 'info':
        config.miner_agent.get_stake_info(miner_address=ethereum_address,
                                   stake_index=stake_index)

    elif action == 'start':
        protocol = UrsulaProcessProtocol()
        reactor.spawnProcess(protocol, "python", ["run_ursula"])
        config.simulation_running = True

    elif action == 'confirm-activity':
        config.miner_agent.confirm_activity(node_address=ethereum_address)

    # elif action == 'divide-stake':
    #     config.miner_agent.divide_stake(miner_address=ethereum_address,
    #                              stake_index=stake_index,
    #                              target_value=target,
    #                              periods=periods)
    #
    # elif action == 'collect-reward':
    #     config.miner_agent.collect_staking_reward(collector_address=withdraw_address)


@cli.command()
@click.argument('action')
@click.option('--nodes', help="The number of nodes to simulate")
@uses_config
def simulation(config, action, nodes):
    """Simulate the nucypher blockchain network"""

    if action == 'start':
        if config.simulation_running is True:
            raise RuntimeError("Network simulation already running")

        click.echo("Bootstrapping blockchain network")
        three_agents = bootstrap_fake_network()

        click.echo("Starting SimulationProtocol")
        for index in range(int(nodes)):
            simulationProtocol = SimulatedUrsulaProcessProtocol()
            reactor.spawnProcess(simulationProtocol, "python", ["run_ursula"])
        config.simulation_running = True

    elif action == 'stop':
        if config.simulation_running is not True:
            raise RuntimeError("Network simulation is not running")
        config.simulation_running = False


@cli.command()
@uses_config
def status(config):

    payload = """
    
    | {chain_type} Interface |
     
    Status ................... {connection}
    Provider Type ............ {provider_type}    
    Etherbase ................ {etherbase}
    Local Accounts ........... {accounts}
    
    
    | NuCypher ETH Contracts |
    
    Registry Path ............ {registry_filepath}
    NucypherToken ............ {token}
    MinerEscrow .............. {escrow}
    PolicyManager ............ {manager}
        
    | Blockchain Network |
    
    Current Period ........... {period}
    Active Staking Ursulas ... {ursulas}
    
    | Swarm |
    
    Known Nodes .............. 
    Verified Nodes ........... 
    Phantom Nodes ............ NotImplemented
    
    
    """.format(report_time=maya.now(),
               chain_type=config.blockchain.__class__.__name__,
               connection='Connected' if config.blockchain.interface.is_connected else 'No Connection',
               registry_filepath=config.blockchain.interface.registry_filepath,
               etherbase=config.accounts[0],
               accounts=len(config.accounts),
               token=config.token_agent.contract_address,
               escrow=config.miner_agent.contract_address,
               manager=config.policy_agent.contract_address,
               provider_type=config.blockchain.interface.provider_type,
               period=config.miner_agent.get_current_period(),
               ursulas=config.miner_agent.get_miner_population())

    click.echo(payload)


if __name__ == "__main__":
    cli()
