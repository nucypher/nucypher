import os

import click
from twisted.internet import reactor
from umbral.config import set_default_curve

set_default_curve()

from nucypher.config.utils import parse_nucypher_ini_config, validate_nucypher_ini_config
from tests.utilities.simulate import SimulatedUrsulaProcessProtocol

__version__ = '0.1.0-mock'  # TODO

DEFAULT_CONF_FILEPATH = '.'

blockchain_stakes = ['Ribeye',
                     'Tri-tip',
                     'Serlion',
                     'Filet Mingion']


class NucypherClickConfig:

    def __init__(self):

        self.verbose = True
        self.config_filepath = './.nucypher.ini'

        # Connect to blockchain
        if not os.path.isfile(self.config_filepath):
            raise RuntimeError("No such config file {}".format(self.config_filepath))

        self.payload = parse_nucypher_ini_config(filepath=self.config_filepath)
        self.blockchain = self.payload['blockchain']

        self.accounts = self.blockchain.interface.w3.eth.accounts

        if self.payload['tester'] and self.payload['deploy']:
            self.blockchain.interface.deployer_address = self.accounts[0]


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
@uses_config
def stakes(config, action, ethereum_address):
    """Manage active node stakes on the blockchain"""

    if action == 'list':
        for index, stake_info in enumerate(blockchain_stakes):
            row = '{} | {}'.format(index, stake_info)
            click.echo(row)


@cli.command()
@click.argument('action')
@click.option('--local', help="Run the simulation thread pool in a subprocess", is_flag=True)
@click.option('--remote', help="Run the simulation on remote hosts", is_flag=True)
@uses_config
def simulate(config, action, async):
    """Simulate the nucypher blockchain network"""

    if action == 'start':
        if config.simulation_running is True:
            raise RuntimeError("Network simulation already running")

        if async:
            print("Starting SimulationProtocol")
            simulationProtocol = SimulatedUrsulaProcessProtocol()
            reactor.spawnProcess(simulationProtocol, "nucypher-cli", ["stake"])
            config.simulation_running = True

        else:
            pass

    elif action == 'stop':
        if config.simulation_running is not True:
            raise RuntimeError("Network simulation is not running")

        print("Joining threadpool")
        for address, t in config.tpool.items():
            if t.is_alive():
                t.join()
            print("Joining {}:{}".format(address, t))
        else:
            print("Simulation Ended")

        config.simulation_running = False


if __name__ == "__main__":
    cli()
