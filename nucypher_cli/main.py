"""NuCypher CLI"""

__version__ = '0.1.0-mock'

BANNER = """
                                  _               
                                 | |              
     _ __  _   _  ___ _   _ _ __ | |__   ___ _ __ 
    | '_ \| | | |/ __| | | | '_ \| '_ \ / _ \ '__|
    | | | | |_| | (__| |_| | |_) | | | |  __/ |   
    |_| |_|\__,_|\___|\__, | .__/|_| |_|\___|_|   
                       __/ | |                    
                      |___/|_|      
                                    
    version {}

""".format(__version__)


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
        self.accounts = self.blockchain.interface.w3.eth.accounts

        if self.payload['tester'] and self.payload['deploy']:
            self.blockchain.interface.deployer_address = self.accounts[0]

        # Three agents
        self.token_agent = None
        self.miner_agent = None
        self.policy_agent = None

    def adhere_agents(self):
        self.token_agent = NucypherTokenAgent(blockchain=self.blockchain)
        self.miner_agent = MinerAgent(token_agent=self.token_agent)
        self.policy_agent = PolicyAgent(miner_agent=self.miner_agent)

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

    click.echo(BANNER)

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
@click.option('--wallet-address', help="The account to lock/unlock instead of the default")
@uses_config
def accounts(config, action, wallet_address):
    """Manage ethereum node accounts"""

    if action == 'list':
        for index, address in enumerate(config.accounts):
            if index == 0:
                row = 'etherbase | {}'.format(address)
            else:
                row = '{} ....... | {}'.format(index, address)
            click.echo(row)

    elif action == 'unlock':
        pass

    elif action == 'lock':
        pass


@cli.command()
@click.argument('action', default='list', required=False)
@click.argument('value', required=False)
@click.argument('periods', required=False)
@click.option('--stake-index', help="The zero-based stake index for this address")
@click.option('--wallet-address', help="Send rewarded tokens to a specific address, instead of the default.")
@uses_config
def stake(config, action, wallet_address, stake_index, value, periods):
    """
    Manage active and inactive node blockchain stakes.

    Arguments
    ==========

    action - Which action to perform; The choices are:

        - list: List all stakes for this node
        - info: Display info about a specific stake
        - start: Start the staking daemon
        - confirm-activity: Manually confirm-activity for the current period
        - divide-stake: Divide an existing stake

    value - The quantity of tokens to stake.

    periods - The duration (in periods) of the stake.

    Options
    ========

    --wallet-address - A valid ethereum checksum address to use instead of the default
    --stake-index - The zero-based stake index, or stake tag for this wallet-address

    """

    if not wallet_address:
        wallet_address = config.blockchain.interface.w3.eth.etherbase

    if action == 'list':
        live_stakes = config.miner_agent.get_all_stakes(miner_address=wallet_address)
        for index, stake_info in enumerate(live_stakes):
            row = '{} | {}'.format(index, stake_info)
            click.echo(row)

    elif action == 'info':
        config.miner_agent.get_stake_info(miner_address=wallet_address,
                                          stake_index=stake_index)

    elif action == 'start':
        protocol = UrsulaProcessProtocol()
        reactor.spawnProcess(protocol, "python", ["run_ursula"])
        config.simulation_running = True

    elif action == 'confirm-activity':
        config.miner_agent.confirm_activity(node_address=wallet_address)

    elif action == 'divide-stake':
        config.miner_agent.divide_stake(miner_address=wallet_address,
                                        stake_index=stake_index,
                                        value=value,
                                        periods=periods)

    elif action == 'collect-reward':
        config.miner_agent.collect_staking_reward(collector_address=wallet_address)


@cli.command()
@click.argument('action')
@click.option('--nodes', help="The number of nodes to simulate")
@click.option('--duration', help="The number of periods to run the simulation for")
@uses_config
def simulation(config, action, nodes, duration):
    """
    Simulate the nucypher blockchain network

    Arguments
    ==========

    action - Which action to perform; The choices are:
        - start: Start a multi-process nucypher network simulation
        - stop: Stop a running simulation gracefully

    Options
    ========

    --nodes - The quantity of nodes (processes) to execute during the simulation
    --duration = The number of periods to run the simulation before termination

    """

    if action == 'start':
        if config.simulation_running is True:
            raise RuntimeError("Network simulation already running")

        click.echo("Bootstrapping blockchain network")
        three_agents = bootstrap_fake_network(blockchain=config.blockchain)
        config.adhere_agents()

        click.echo("Starting SimulationProtocol")
        for index in range(int(nodes)):
            simulationProtocol = SimulatedUrsulaProcessProtocol()

            # args = ["run_ursula", "ipc:///tmp/geth.ipc", "https://127.0.0.1:5551"]
            reactor.spawnProcess(simulationProtocol, "python", ['run_ursula'])

            config.simulation_running = True

    elif action == 'stop':
        if config.simulation_running is not True:
            raise RuntimeError("Network simulation is not running")
        config.simulation_running = False


@cli.command()
@click.option('--provider', help="Echo blockchain provider info", is_flag=True)
@click.option('--contracts', help="Echo nucypher smart contract info", is_flag=True)
@click.option('--network', help="Echo the network status", is_flag=True)
@uses_config
def status(config, provider, contracts, network, all):
    """
    Echo a snapshot of live network metadata.
    """

    provider_payload = """

    | {chain_type} Interface |
     
    Status ................... {connection}
    Provider Type ............ {provider_type}    
    Etherbase ................ {etherbase}
    Local Accounts ........... {accounts}

    """.format(chain_type=config.blockchain.__class__.__name__,
               connection='Connected' if config.blockchain.interface.is_connected else 'No Connection',
               provider_type=config.blockchain.interface.provider_type,
               etherbase=config.accounts[0],
               accounts=len(config.accounts))

    contract_payload = """
    
    | NuCypher ETH Contracts |
    
    Registry Path ............ {registry_filepath}
    NucypherToken ............ {token}
    MinerEscrow .............. {escrow}
    PolicyManager ............ {manager}
        
    """.format(registry_filepath=config.blockchain.interface.registry_filepath,
               token=config.token_agent.contract_address,
               escrow=config.miner_agent.contract_address,
               manager=config.policy_agent.contract_address,
               period=config.miner_agent.get_current_period())

    network_payload = """
    
    | Blockchain Network |
    
    Current Period ........... {period}
    Active Staking Ursulas ... {ursulas}
    
    | Swarm |
    
    Known Nodes .............. 
    Verified Nodes ........... 
    Phantom Nodes ............ NotImplemented
        
    
    """.format(period=config.miner_agent.get_current_period(),
               ursulas=config.miner_agent.get_miner_population())

    subpayloads = ((provider, provider_payload),
                   (contracts, contract_payload),
                   (network, network_payload),
                   )

    if not any(sp[0] for sp in subpayloads):
        payload = ''.join(sp[1] for sp in subpayloads)
    else:
        payload = str()
        for requested, subpayload in subpayloads:
            if requested is True:
                payload += subpayload

    click.echo(payload)


if __name__ == "__main__":
    cli()
