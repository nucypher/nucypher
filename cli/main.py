#!/usr/bin/env python3

import asyncio
import logging
import random
import shutil
import sys

import subprocess
from urllib.parse import urlparse

from constant_sorrow import constants

from nucypher.blockchain.eth.actors import Miner
from nucypher.blockchain.eth.chains import Blockchain, TesterBlockchain
from nucypher.blockchain.eth.deployers import NucypherTokenDeployer, MinerEscrowDeployer, PolicyManagerDeployer
from nucypher.characters import Ursula
from nucypher.config.constants import DEFAULT_CONFIG_ROOT, DEFAULT_SIMULATION_PORT, \
    DEFAULT_SIMULATION_REGISTRY_FILEPATH, DEFAULT_INI_FILEPATH, DEFAULT_REST_PORT, DEFAULT_DB_NAME, \
    BASE_DIR
from nucypher.config.metadata import write_node_metadata, collect_stored_nodes
from nucypher.config.parsers import parse_nucypher_ini_config, parse_running_modes
from nucypher.utilities.sandbox import UrsulaProcessProtocol

__version__ = '0.1.0-alpha.0'

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

import os
import click
from twisted.internet import reactor

from nucypher.blockchain.eth.agents import MinerAgent, PolicyAgent, NucypherTokenAgent
from nucypher.utilities.blockchain import token_airdrop
from nucypher.config.utils import validate_nucypher_ini_config, initialize_configuration, NucypherConfigurationError

root = logging.getLogger()
root.setLevel(logging.DEBUG)

ch = logging.StreamHandler(sys.stdout)
ch.setLevel(logging.INFO)
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
ch.setFormatter(formatter)
root.addHandler(ch)


class NucypherClickConfig:

    def __init__(self, operating_mode='federated', simulation_mode=False, use_config=False):

        self.config_filepath = DEFAULT_INI_FILEPATH  # TODO
        # click.echo("Using configuration filepath {}".format(self.config_filepath))

        self.operating_mode = operating_mode
        self.simulation_mode = simulation_mode

        # Set operating and run modes
        if use_config is True:
            operating_modes = parse_running_modes(filepath=self.config_filepath)

        if self.simulation_mode is True:
            simulation_running = False
            sim_registry_filepath = DEFAULT_SIMULATION_REGISTRY_FILEPATH
        else:
            simulation_running = constants.SIMULATION_DISABLED
            sim_registry_filepath = constants.SIMULATION_DISABLED

        self.simulation_running = simulation_running
        self.sim_registry_filepath = sim_registry_filepath
        self.sim_processes = list()

        sim_mode = 'simulation' if self.simulation_mode else 'live'
        click.echo("Running in {} {} mode".format(sim_mode, self.operating_mode))

        if use_config is True:
            self.payload = parse_nucypher_ini_config(filepath=self.config_filepath)
            click.echo("Successfully parsed configuration file")

        # Blockchain connection contract agency
        self.blockchain = constants.NO_BLOCKCHAIN_CONNECTION
        self.accounts = constants.NO_BLOCKCHAIN_CONNECTION
        self.token_agent = constants.NO_BLOCKCHAIN_CONNECTION
        self.miner_agent = constants.NO_BLOCKCHAIN_CONNECTION
        self.policy_agent = constants.NO_BLOCKCHAIN_CONNECTION

    def connect_to_blockchain(self):
        """Initialize all blockchain entities from parsed config values"""

        self.blockchain = Blockchain.from_config(filepath=self.config_filepath)
        self.accounts = self.blockchain.interface.w3.eth.accounts

        #TODO: Exception handling here for key error when using incompadible operating mode
        if self.payload['tester'] and self.payload['deploy']:
            self.blockchain.interface.deployer_address = self.accounts[0]

    def connect_to_contracts(self, simulation: bool=False):
        """Initialize contract agency and set them on config"""

        if simulation is True:
            self.blockchain.interface._registry._swap_registry(filepath=self.sim_registry_filepath)

        self.token_agent = NucypherTokenAgent(blockchain=self.blockchain)
        self.miner_agent = MinerAgent(token_agent=self.token_agent)
        self.policy_agent = PolicyAgent(miner_agent=self.miner_agent)

    @property
    def rest_uri(self):
        host, port = self.payload['rest_host'], self.payload['rest_port']
        uri_template = "http://{}:{}"
        return uri_template.format(host, port)

    @property
    def dht_uri(self):
        host, port = self.payload['dht_host'], self.payload['dht_port']
        uri_template = "http://{}:{}"
        return uri_template.format(host, port)


uses_config = click.make_pass_decorator(NucypherClickConfig, ensure=True)


@click.group()
@click.option('--version', help="Prints the installed version.", is_flag=True)
@click.option('--verbose', help="Enable verbose mode.", is_flag=True)
@click.option('--config-file', help="Specify a custom config filepath.", type=click.Path(), default=DEFAULT_INI_FILEPATH)
@uses_config
def cli(config, verbose, version, config_file):
    """Configure and manage a nucypher nodes"""

    # validate_nucypher_ini_config(filepath=config_file)

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
def config(action, config_file):
    """Manage the nucypher .ini configuration file"""

    def destroy():
        click.confirm("Permanently destroy all nucypher configurations, known nodes, certificates and keys?", abort=True)
        shutil.rmtree(DEFAULT_CONFIG_ROOT, ignore_errors=True)
        click.echo("Deleted configuration files at {}".format(DEFAULT_CONFIG_ROOT))

    def initialize():
        click.confirm("Initialize new nucypher configuration?", abort=True)
        try:
            initialize_configuration(config_root=DEFAULT_CONFIG_ROOT)
        except FileExistsError:
            raise NucypherConfigurationError("There is an existing configuration.")
        click.echo("Created configuration files at {}".format(DEFAULT_CONFIG_ROOT))

    if action == "validate":
        validate_nucypher_ini_config(config_file)

    elif action == "init":
        initialize()

    elif action == "destroy":
        destroy()

    elif action == "reset":
        destroy()
        initialize()


@cli.command()
@click.argument('action', default='list', required=False)
@click.option('--address', help="The account to lock/unlock instead of the default")
@uses_config
def accounts(config, action, address):
    """Manage ethereum node accounts"""

    if action == 'list':
        for index, address in enumerate(config.accounts):
            if index == 0:
                row = 'etherbase | {}'.format(address)
            else:
                row = '{} ....... | {}'.format(index, address)
            click.echo(row)

    elif action == 'unlock':
        # passphrase = click.prompt("Enter passphrase to unlock {}".format(address))
        raise NotImplementedError

    elif action == 'lock':

        # click.confirm("Lock {}?".format(address))
        raise NotImplementedError

    elif action == 'balance':
        raise NotImplementedError


@cli.command()
@click.argument('action', default='list', required=False)
@click.option('--address', help="Send rewarded tokens to a specific address, instead of the default.")
@click.option('--value', help="Stake value in the smallest denomination")
@click.option('--duration', help="Stake duration in periods")
@click.option('--index', help="A specific stake index to resume")
@uses_config
def stake(config, action, address, index, value, duration):
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

    config.connect_to_contracts()

    if not address:

        for index, address in enumerate(config.accounts):
            if index == 0:
                row = 'etherbase (0) | {}'.format(address)
            else:
                row = '{} .......... | {}'.format(index, address)
            click.echo(row)

        click.echo("Select ethereum address")
        account_selection = click.prompt("Enter 0-{}".format(len(config.accounts)), type=int)
        address = config.accounts[account_selection]

    if action == 'list':
        live_stakes = config.miner_agent.get_all_stakes(miner_address=address)
        for index, stake_info in enumerate(live_stakes):
            row = '{} | {}'.format(index, stake_info)
            click.echo(row)

    elif action == 'init':
        click.confirm("Stage a new stake?", abort=True)

        live_stakes = config.miner_agent.get_all_stakes(miner_address=address)
        if len(live_stakes) > 0:
            raise RuntimeError("There is an existing stake for {}".format(address))

        # Value
        balance = config.token_agent.get_balance(address=address)
        click.echo("Current balance: {}".format(balance))
        value = click.prompt("Enter stake value", type=int)

        # Duration
        message = "Minimum duration: {} | Maximum Duration: {}".format(constants.MIN_LOCKED_PERIODS,
                                                                       constants.MAX_REWARD_PERIODS)
        click.echo(message)
        duration = click.prompt("Enter stake duration in days", type=int)

        start_period = config.miner_agent.get_current_period()
        end_period = start_period + duration

        # Review
        click.echo("""
        
        | Staged Stake |
        
        Node: {address}
        Value: {value}
        Duration: {duration}
        Start Period: {start_period}
        End Period: {end_period}
        
        """.format(address=address,
                   value=value,
                   duration=duration,
                   start_period=start_period,
                   end_period=end_period))

        if not click.confirm("Is this correct?"):
            # field = click.prompt("Which stake field do you want to edit?")
            raise NotImplementedError

        # Initialize the staged stake
        config.miner_agent.deposit_tokens(amount=value, lock_periods=duration, sender_address=address)

        proc_params = ['run_ursula']
        processProtocol = UrsulaProcessProtocol(command=proc_params)
        ursula_proc = reactor.spawnProcess(processProtocol, "nucypher-cli", proc_params)

    elif action == 'resume':
        """Reconnect and resume an existing live stake"""

        proc_params = ['run_ursula']
        processProtocol = UrsulaProcessProtocol(command=proc_params)
        ursula_proc = reactor.spawnProcess(processProtocol, "nucypher-cli", proc_params)

    elif action == 'confirm-activity':
        """Manually confirm activity for the active period"""

        stakes = config.miner_agent.get_all_stakes(miner_address=address)
        if len(stakes) == 0:
            raise RuntimeError("There are no active stakes for {}".format(address))
        config.miner_agent.confirm_activity(node_address=address)

    elif action == 'divide':
        """Divide an existing stake by specifying the new target value and end period"""

        stakes = config.miner_agent.get_all_stakes(miner_address=address)
        if len(stakes) == 0:
            raise RuntimeError("There are no active stakes for {}".format(address))

        if not index:
            for selection_index, stake_info in enumerate(stakes):
                click.echo("{} ....... {}".format(selection_index, stake_info))
            index = click.prompt("Select a stake to divide", type=int)

        target_value = click.prompt("Enter new target value", type=int)
        extension = click.prompt("Enter number of periods to extend", type=int)

        click.echo("""
        Current Stake: {}
        
        New target value {}
        New end period: {}
        
        """.format(stakes[index],
                   target_value,
                   target_value+extension))

        click.confirm("Is this correct?", abort=True)
        config.miner_agent.divide_stake(miner_address=address,
                                        stake_index=index,
                                        value=value,
                                        periods=extension)

    elif action == 'collect-reward':
        """Withdraw staking reward to the specified wallet address"""
        # click.confirm("Send {} to {}?".format)
        # config.miner_agent.collect_staking_reward(collector_address=address)
        raise NotImplementedError

    elif action == 'abort':
        click.confirm("Are you sure you want to abort the staking process?", abort=True)
        # os.kill(pid=NotImplemented)
        raise NotImplementedError



@cli.command()
@click.argument('action')
@click.option('--federated-only', is_flag=True)
@click.option('--nodes', help="The number of nodes to simulate", type=int)
@uses_config
def simulate(config, action, nodes, federated_only):
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

    if action == 'init':

        # OK, Try connecting to the blockchain
        click.echo("Connecting to provider endpoint")
        config.connect_to_blockchain()

        # Actual simulation setup logic
        one_million_eth = 10 ** 6 * 10 ** 18
        click.echo("Airdropping {} ETH to {} test accounts".format(one_million_eth, len(config.accounts)))
        config.blockchain.ether_airdrop(amount=one_million_eth)  # wei -> ether | 1 Million ETH

        # Fin
        click.echo("Blockchain initialized")

    if action == 'deploy':

        if config.simulation_running is True:
            raise RuntimeError("Network simulation already running")

        if not federated_only:
            config.connect_to_blockchain()

            click.confirm("Deploy all nucypher contracts to blockchain?", abort=True)
            click.echo("Bootstrapping simulated blockchain network")

            blockchain = TesterBlockchain.from_config()

            # TODO: Enforce Saftey - ensure this is "fake" #
            conditions = ()
            assert True

            # Parse addresses
            etherbase, *everybody_else = blockchain.interface.w3.eth.accounts

            # Deploy contracts
            token_deployer = NucypherTokenDeployer(blockchain=blockchain, deployer_address=etherbase)
            token_deployer.arm()
            token_deployer.deploy()
            token_agent = token_deployer.make_agent()
            click.echo("Deployed {}:{}".format(token_agent.contract_name, token_agent.contract_address))

            miner_escrow_deployer = MinerEscrowDeployer(token_agent=token_agent, deployer_address=etherbase)
            miner_escrow_deployer.arm()
            miner_escrow_deployer.deploy()
            miner_agent = miner_escrow_deployer.make_agent()
            click.echo("Deployed {}:{}".format(miner_agent.contract_name, miner_agent.contract_address))

            policy_manager_deployer = PolicyManagerDeployer(miner_agent=miner_agent, deployer_address=etherbase)
            policy_manager_deployer.arm()
            policy_manager_deployer.deploy()
            policy_agent = policy_manager_deployer.make_agent()
            click.echo("Deployed {}:{}".format(policy_agent.contract_name, policy_agent.contract_address))

            airdrop_amount = 1000000 * int(constants.M)
            click.echo("Airdropping tokens {} to {} addresses".format(airdrop_amount, len(everybody_else)))
            _receipts = token_airdrop(token_agent=token_agent,
                                      origin=etherbase,
                                      addresses=everybody_else,
                                      amount=airdrop_amount)

            click.echo("Connecting to deployed contracts")
            config.connect_to_contracts()

            # Commit the current state of deployment to a registry file.
            click.echo("Writing filesystem registry")
            _sim_registry_name = config.blockchain.interface._registry.commit(filepath=DEFAULT_SIMULATION_REGISTRY_FILEPATH)

            # Fin
            click.echo("Ready to simulate decentralized swarm.")

        else:
            click.echo("Ready to run federated swarm.")

    elif action == 'swarm':

        if not federated_only:
            config.connect_to_blockchain()
            config.connect_to_contracts(simulation=True)

        localhost = 'localhost'

        # Select a port range to use on localhost for sim servers
        start_port, stop_port = DEFAULT_SIMULATION_PORT, DEFAULT_SIMULATION_PORT + int(nodes)
        port_range = range(start_port, stop_port)
        click.echo("Selected local ports {}-{}".format(start_port, stop_port))

        for index, sim_port_number in enumerate(port_range):

            #
            # Parse ursula parameters
            #

            rest_port, dht_port = sim_port_number, sim_port_number + 100
            db_name = 'sim-{}'.format(rest_port)

            cli_exec = os.path.join(BASE_DIR, 'cli', 'main.py')
            python_exec = 'python'

            proc_params = '''
            python3 {} run_ursula --host {} --rest-port {} --dht-port {} --db-name {}
            '''.format(python_exec, cli_exec, localhost, rest_port, dht_port, db_name).split()

            if federated_only:
                click.echo("Setting federated operating mode")
                proc_params.append('--federated-only')
            else:
                sim_address = config.accounts[index+1]
                miner = Miner(miner_agent=config.miner_agent, checksum_address=sim_address)

                # stake a random amount
                min_stake, balance = constants.MIN_ALLOWED_LOCKED, miner.token_balance
                value = random.randint(min_stake, balance)

                # for a random lock duration
                min_locktime, max_locktime = constants.MIN_LOCKED_PERIODS, constants.MAX_MINTING_PERIODS
                periods = random.randint(min_locktime, max_locktime)

                miner.initialize_stake(amount=value, lock_periods=periods)
                click.echo("{} Initialized new stake: {} tokens for {} periods".format(sim_address, value, periods))

                proc_params.extend('--checksum-address {}'.format(sim_address).split())

            # Spawn
            click.echo("Spawning node #{}".format(index+1))
            processProtocol = UrsulaProcessProtocol(command=proc_params)
            cli_exec = os.path.join(BASE_DIR, 'cli', 'main.py')
            ursula_proc = reactor.spawnProcess(processProtocol, cli_exec, proc_params)
            config.sim_processes.append(ursula_proc)

            #
            # post-spawnProcess
            #

            # Start with some basic status data, then build on it

            rest_uri = "http://{}:{}".format(localhost, rest_port)
            dht_uri = "http://{}:{}".format(localhost, dht_port)

            sim_data = "Started simulated Ursula | ReST {} | DHT {} ".format(rest_uri, dht_uri)
            rest_uri = "{host}:{port}".format(host=localhost, port=str(sim_port_number))
            dht_uri = '{host}:{port}'.format(host=localhost, port=dht_port)
            sim_data.format(rest_uri, dht_uri)

            if not federated_only:
                stake_infos = tuple(config.miner_agent.get_all_stakes(miner_address=sim_address))
                sim_data += '| ETH address {}'.format(sim_address)
                sim_data += '| {} Active stakes '.format(len(stake_infos))

            click.echo(sim_data)
            config.simulation_running = True

        click.echo("Starting the reactor")
        try:
            reactor.run()

        finally:

            if config.operating_mode == 'decentralized':
                click.echo("Removing simulation registry")
                os.remove(config.sim_registry_filepath)

            click.echo("Stopping simulated Ursula processes")
            for process in config.sim_processes:
                os.kill(process.pid, 9)
                click.echo("Killed {}".format(process))
            config.simulation_running = False
            click.echo("Simulation stopped")

    elif action == 'stop':
        # Kill the simulated ursulas TODO: read PIDs from storage?
        if config.simulation_running is not True:
            raise RuntimeError("Network simulation is not running")

        for process in config.ursula_processes:
            process.transport.signalProcess('KILL')
        else:
            # TODO: Confirm they are dead
            config.simulation_running = False

    elif action == 'status':

        if not config.simulation_running:
            status_message = "Simulation not running."
        else:

            ursula_processes = len(config.ursula_processes)

            status_message = """
            
            | Node Swarm Simulation Status |
            
            Simulation processes .............. {}
            
            """.format(ursula_processes)

        click.echo(status_message)

    elif action == 'demo':
        """Run the finnegans wake demo"""
        demo_exec = os.path.join(BASE_DIR, 'cli', 'demos', 'finnegans-wake-demo.py')
        process_args = [sys.executable, demo_exec]

        if federated_only:
            process_args.append('--federated-only')

        subprocess.run(process_args, stdout=subprocess.PIPE)


@cli.command()
@click.option('--provider', help="Echo blockchain provider info", is_flag=True)
@click.option('--contracts', help="Echo nucypher smart contract info", is_flag=True)
@click.option('--network', help="Echo the network status", is_flag=True)
@uses_config
def status(config, provider, contracts, network):
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


@cli.command()
@click.option('--federated-only', is_flag=True, default=False)
@click.option('--teacher-uri', type=str)
@click.option('--seed-node', is_flag=True, default=False)
@click.option('--rest-host', type=str, default='localhost')
@click.option('--rest-port', type=int, default=DEFAULT_REST_PORT)
@click.option('--db-name', type=str, default=DEFAULT_DB_NAME)
@click.option('--checksum-address', type=str)
@click.option('--data-dir', type=click.Path(), default=DEFAULT_CONFIG_ROOT)
@click.option('--config-file', type=click.Path(), default=DEFAULT_INI_FILEPATH)
def run_ursula(rest_port,
               rest_host,
               dht_port,
               db_name,
               teacher_uri,
               checksum_address,
               federated_only,
               seed_node,
               data_dir,
               config_file) -> None:
    """

    The following procedure is required to "spin-up" an Ursula node.

        1. Collect all known known from storages
        2. Start the asyncio event loop
        3. Initialize Ursula object
        5. Enter the learning loop
        6. Run TLS deployment
        7. Start the staking daemon

    Configurable values are first read from the .ini configuration file,
    but can be overridden (mostly for testing purposes) with inline cli options.

    """

    other_nodes = collect_stored_nodes(federated_only=federated_only)  # 1. Collect known nodes

    ursula_params = dict(federated_only=federated_only,
                         known_nodes=other_nodes,
                         rest_host=rest_host,
                         rest_port=rest_port,
                         dht_port=dht_port,
                         db_name=db_name,
                         checksum_address=checksum_address)

    asyncio.set_event_loop(asyncio.new_event_loop())  # 2. Init DHT async loop

    if teacher_uri:
        host, port = teacher_uri.split(':')
        teacher = Ursula(rest_host=host,
                         rest_port=port,
                         db_name='ursula-{}.db'.format(rest_port),
                         federated_only=federated_only)

        ursula_params['known_nodes'] = (teacher, )

    # 3. Initialize Ursula (includes overrides)
    ursula = Ursula(**ursula_params)

    write_node_metadata(seed_node=seed_node, node=ursula, node_metadata_dir=data_dir)

    ursula.start_learning_loop()      # 5. Enter learning loop
    ursula.get_deployer().run()       # 6. Run TLS Deployer

    if not federated_only:
        ursula.stake()                # 7. start staking daemon


if __name__ == "__main__":
    cli()
