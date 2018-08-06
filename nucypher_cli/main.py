"""NuCypher CLI"""


import asyncio

from constant_sorrow import constants

from nucypher.characters import Ursula
from nucypher.config.constants import DEFAULT_CONFIG_ROOT, DEFAULT_SIMULATION_PORT, \
    DEFAULT_SIMULATION_REGISTRY_FILEPATH, DEFAULT_INI_FILEPATH
from nucypher.config.metadata import write_node_metadata, collect_stored_nodes
from nucypher.config.parsers import parse_nucypher_ini_config

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


import os
import click
from twisted.internet import reactor

from nucypher.blockchain.eth.agents import MinerAgent, PolicyAgent, NucypherTokenAgent
from nucypher.utilities.blockchain import bootstrap_fake_network, spawn_random_miners
from nucypher.config.utils import validate_nucypher_ini_config, initialize_configuration
from nucypher.utilities.simulate import UrsulaStakingProtocol


class NucypherClickConfig:

    def __init__(self):

        # Set runtime defaults
        self.verbose = True
        self.config_filepath = './.nucypher.ini'

        # Set simulation defaults
        self.simulation_running = False
        self.ursula_processes = list()

        click.echo("Parsing {}".format(self.config_filepath))
        self.payload = parse_nucypher_ini_config(filepath=self.config_filepath)
        self.operating_mode = self.payload['operating_mode']

        if self.operating_mode == 'decentralized':

            # FIXME: Detect no .ipc file
            if not os.path.isfile(self.config_filepath):
                raise RuntimeError("No such config file {}".format(self.config_filepath))

            self.blockchain = self.payload['blockchain']
            self.accounts = self.blockchain.interface.w3.eth.accounts

            if self.payload['tester'] and self.payload['deploy']:
                self.blockchain.interface.deployer_address = self.accounts[0]

            # Three agents
            self.token_agent = None
            self.miner_agent = None
            self.policy_agent = None

    def adhere_agents(self):

        token_agent = NucypherTokenAgent(blockchain=self.blockchain)
        miner_agent = MinerAgent(token_agent=token_agent)
        policy_agent = PolicyAgent(miner_agent=miner_agent)

        self.token_agent = token_agent
        self.miner_agent = miner_agent
        self.policy_agent = policy_agent

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
@click.option('--data-dir', help="Specify a custom runtime directory")
@uses_config
def config(config, action, config_file, data_dir):
    """Manage the nucypher .ini configuration file"""

    if action == "validate":
        validate_nucypher_ini_config(config_file)

    if action == "init":
        click.confirm("Initialize new nucypher configuration?", abort=True)
        config_root = data_dir if data_dir else DEFAULT_CONFIG_ROOT
        initialize_configuration(config_root=config_root)
        click.echo("Created configuration files at {}".format(config_root))


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

    config.adhere_agents()  # TODO: better place to do this?

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

        processProtocol = UrsulaStakingProtocol()
        proc_params = ['run_ursula']
        ursula_proc = reactor.spawnProcess(processProtocol, "nucypher-cli", proc_params)

    elif action == 'resume':
        """Reconnect and resume an existing live stake"""

        processProtocol = UrsulaStakingProtocol()
        proc_params = ['run_ursula']
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
@click.option('--nodes', help="The number of nodes to simulate", type=int)
# @click.option('--periods', help="The number of periods to run the simulation for")
@uses_config
def simulation(config, action, nodes):
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

        click.echo("Bootstrapping simulated blockchain network")
        _three_agents = bootstrap_fake_network(blockchain=config.blockchain, airdrop=True)

        click.echo("Establishing connection to ethereum contracts")
        config.adhere_agents()

        # Commit the current state of deployment to a registry file.
        click.echo("Saving filesystem registry")
        _sim_registry_name = config.blockchain.interface._registry.commit(filepath=DEFAULT_SIMULATION_REGISTRY_FILEPATH)

        sim_accounts = config.accounts[1:int(nodes)+1]

        # Select a port range to use on localhost for sim servers
        start_port, stop_port = DEFAULT_SIMULATION_PORT, DEFAULT_SIMULATION_PORT + int(nodes)
        click.echo("Selected local ports {}-{}".format(start_port, stop_port))

        seed_miner, *sim_miners = spawn_random_miners(miner_agent=config.miner_agent, addresses=sim_accounts)

        click.echo("Selecting sim ethereum accounts")
        for sim_port_number, sim_miner in enumerate(sim_miners, start=start_port):

            rest_port, dht_port = sim_port_number, sim_port_number + 100
            db_name = 'sim-{}'.format(rest_port)

            processProtocol = UrsulaStakingProtocol()

            raw_proc_params = '''
            run_ursula --host 127.0.0.1 --rest-port {} --dht-port {} --db-name {} --checksum-address {}
            '''.format(rest_port, dht_port, db_name, sim_miner.checksum_public_address)
            proc_params = raw_proc_params.split()

            import ipdb; ipdb.set_trace()

            ursula_proc = reactor.spawnProcess(processProtocol, "nucypher-cli", proc_params)

            config.ursula_processes.append(ursula_proc)

            rest_uri = "https://127.0.0.1:{}".format(str(sim_port_number), sim_miner.checksum_public_address)

            stake_infos = tuple(config.miner_agent.get_all_stakes(miner_address=sim_miner.checksum_public_address))

            sim_data = "Started simulated Ursula at {} | address {} | stake {}"

            click.echo(sim_data.format(rest_uri, sim_miner.checksum_public_address, stake_infos[0]))
            config.simulation_running = True

        click.echo("Starting the reactor")
        try:
            reactor.run()
        finally:
            click.echo("Stopping simulated Ursula processes")
            for process in config.ursula_processes:
                import ipdb; ipdb.set_trace()
                os.kill(process.pid, 9)
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


@cli.command()
@click.option('--federated-only', is_flag=True, default=False)
@click.option('--seed-node', is_flag=True, default=False)
@click.option('--rest-port', type=int)
@click.option('--dht-port', type=int)
@click.option('--db-name', type=str)
@click.option('--checksum-address', type=str)
@click.option('--data-dir', type=click.Path(), default=DEFAULT_CONFIG_ROOT)
@click.option('--config-file', type=click.Path(), default=DEFAULT_INI_FILEPATH)
def run_ursula(rest_port, dht_port, db_name,
               checksum_address, federated_only,
               seed_node, data_dir, config_file) -> None:
    """
    ======================================================================

    ~ WARNING: DO NOT USE THIS COMMAND DIRECTLY ~

    This is not an actual mining script -
    it is a twisted process handler

    ======================================================================


    This process handler is executed in the main thread using the nucypher-cli,
    implemented with twisted ProcessProtocol and spawnProcess.

    The following procedure is required to "spin-up" an Ursula node.

        1. Collect all known known from storages
        2. Start the asyncio event loop
        3. Initialize Ursula object
        4. Start DHT listener
        5. Enter the learning loop
        6. Run TLS deployment
        7. Start the staking daemon

    Configurable values are first read from the .ini configuration file,
    but can be overridden (mostly for testing purposes) with inline cli options.

    """

    if not seed_node:
        known_nodes, other_nodes = collect_stored_nodes()  # 1. Collect known nodes
    else:
        known_nodes = tuple()

    asyncio.set_event_loop(asyncio.new_event_loop())   # 2. Init DHT async loop

    overrides = dict(federated_only=federated_only,
                     known_nodes=known_nodes,
                     rest_port=rest_port,
                     dht_port=dht_port,
                     db_name=db_name,
                     checksum_address=checksum_address)

    # 3. Initialize Ursula (includes overrides)
    ursula = Ursula.from_config(filepath=config_file,
                                federated_only=federated_only,
                                overrides=overrides)

    ursula.dht_listen()           # 4. Start DHT

    write_node_metadata(node=ursula, node_metadata_dir=data_dir)

    ursula.start_learning_loop()  # 5. Enter learning loop
    ursula.get_deployer().run()   # 6. Run TLS Deployer

    if not federated_only:
        ursula.stake()            # 7. start staking daemon


if __name__ == "__main__":
    cli()
