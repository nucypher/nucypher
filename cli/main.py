#!/usr/bin/env python3
import json
import logging
import os
import random
import sys
from typing import Tuple, ClassVar

import click
import shutil
import subprocess
from constant_sorrow import constants
from cryptography.hazmat.primitives.asymmetric import ec
from eth_utils import is_checksum_address
from twisted.internet import reactor
from web3.middleware import geth_poa_middleware

from nucypher.blockchain.eth.actors import Miner
from nucypher.blockchain.eth.agents import MinerAgent, PolicyAgent, NucypherTokenAgent, EthereumContractAgent
from nucypher.blockchain.eth.chains import Blockchain
from nucypher.blockchain.eth.constants import (DISPATCHER_SECRET_LENGTH,
                                               MIN_ALLOWED_LOCKED,
                                               MIN_LOCKED_PERIODS,
                                               MAX_MINTING_PERIODS)
from nucypher.blockchain.eth.deployers import NucypherTokenDeployer, MinerEscrowDeployer, PolicyManagerDeployer, \
    UserEscrowDeployer, ContractDeployer
from nucypher.blockchain.eth.interfaces import BlockchainDeployerInterface, BlockchainInterface
from nucypher.blockchain.eth.registry import TemporaryEthereumContractRegistry, EthereumContractRegistry
from nucypher.blockchain.eth.sol.compile import SolidityCompiler
from nucypher.config.characters import UrsulaConfiguration
from nucypher.config.constants import BASE_DIR, DEFAULT_CONFIG_FILE_LOCATION
from nucypher.config.keyring import NucypherKeyring
from nucypher.config.node import NodeConfiguration
from nucypher.config.utils import validate_configuration_file
from nucypher.crypto.api import generate_self_signed_certificate, _save_tls_certificate
from nucypher.utilities.sandbox.blockchain import TesterBlockchain, token_airdrop
from nucypher.utilities.sandbox.constants import (DEVELOPMENT_TOKEN_AIRDROP_AMOUNT,
                                                  DEVELOPMENT_ETH_AIRDROP_AMOUNT,
                                                  )
from nucypher.utilities.sandbox.ursula import UrsulaProcessProtocol
import collections

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


#
# Setup Logging
#

root = logging.getLogger()
root.setLevel(logging.DEBUG)

ch = logging.StreamHandler(sys.stdout)
ch.setLevel(logging.INFO)
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
ch.setFormatter(formatter)
root.addHandler(ch)


#
# CLI Configuration
#


class NucypherClickConfig:

    def __init__(self):

        # Node Configuration
        self.node_config = constants.NO_NODE_CONFIGURATION
        self.federated_only = constants.NO_NODE_CONFIGURATION
        self.metadata_dir = constants.NO_NODE_CONFIGURATION

        # Blockchain
        self.deployer = constants.NO_BLOCKCHAIN_CONNECTION
        self.compile = constants.NO_BLOCKCHAIN_CONNECTION
        self.poa = constants.NO_BLOCKCHAIN_CONNECTION
        self.blockchain = constants.NO_BLOCKCHAIN_CONNECTION
        self.provider_uri = constants.NO_BLOCKCHAIN_CONNECTION
        self.registry_filepath = constants.NO_BLOCKCHAIN_CONNECTION
        self.accounts = constants.NO_BLOCKCHAIN_CONNECTION

        # Agency
        self.token_agent = constants.NO_BLOCKCHAIN_CONNECTION
        self.miner_agent = constants.NO_BLOCKCHAIN_CONNECTION
        self.policy_agent = constants.NO_BLOCKCHAIN_CONNECTION

    def connect_to_blockchain(self):
        """Initialize all blockchain entities from parsed config values"""

        #
        # Blockchain Connection
        #
        if not self.federated_only:
            if self.deployer:
                self.registry_filepath = NodeConfiguration.REGISTRY_SOURCE

            if self.compile:
                click.confirm("Compile solidity source?", abort=True)
            self.blockchain = Blockchain.connect(provider_uri=self.provider_uri,
                                                 registry_filepath=self.registry_filepath,
                                                 deployer=self.deployer,
                                                 compile=self.compile)

            self.accounts = self.blockchain.interface.w3.eth.accounts

            if self.poa:
                w3 = self.blockchain.interface.w3
                w3.middleware_stack.inject(geth_poa_middleware, layer=0)

    def connect_to_contracts(self):
        """Initialize contract agency and set them on config"""
        self.token_agent = NucypherTokenAgent(blockchain=self.blockchain)
        self.miner_agent = MinerAgent(token_agent=self.token_agent)
        self.policy_agent = PolicyAgent(miner_agent=self.miner_agent)


uses_config = click.make_pass_decorator(NucypherClickConfig, ensure=True)


@click.group()
@click.option('--version', is_flag=True)
@click.option('--verbose', is_flag=True)
@click.option('--dev', is_flag=True)
@click.option('--federated-only', is_flag=True)
@click.option('--config-root', type=click.Path())
@click.option('--config-file', type=click.Path())
@click.option('--metadata-dir', type=click.Path())
@click.option('--provider-uri', type=str)
@click.option('--compile', is_flag=True)
@click.option('--registry-filepath', type=click.Path())
@click.option('--deployer', is_flag=True)
@click.option('--poa', is_flag=True)
@uses_config
def cli(config,
        verbose,
        version,
        dev,
        federated_only,
        config_root,
        config_file,
        metadata_dir,
        provider_uri,
        registry_filepath,
        deployer,
        compile,
        poa):

    click.echo(BANNER)

    # Store config data
    config.verbose = verbose
    config.dev = dev
    config.federated_only = federated_only
    config.config_root = config_root
    config.config_file = config_file
    config.metadata_dir = metadata_dir
    config.provider_uri = provider_uri
    config.compile = compile
    config.registry_filepath = registry_filepath
    config.deployer = deployer
    config.poa = poa

    if version:
        click.echo("Version {}".format(__version__))

    if config.verbose:
        click.echo("Running in verbose mode...")

    if not config.dev:
        click.echo("WARNING: Development mode is disabled")
    else:
        click.echo("Running in development mode")


@cli.command()
@click.option('--filesystem', is_flag=True, default=False)
@click.argument('action')
@uses_config
def configure(config, action, filesystem):

    def __destroy(configuration):
        if config.dev:
            raise NodeConfiguration.ConfigurationError("Cannot destroy a temporary node configuration")

        click.confirm("*Permanently delete* all nucypher private keys, configurations,"
                      " known nodes, certificates and files at {}?".format(configuration.config_root), abort=True)

        shutil.rmtree(configuration.config_root, ignore_errors=True)
        click.echo("Deleted configuration files at {}".format(node_configuration.config_root))

    def __initialize(configuration):
        if config.dev:
            click.echo("Using temporary storage area")
        click.confirm("Initialize new nucypher configuration?", abort=True)

        configuration.write_defaults()
        click.echo("Created configuration files at {}".format(node_configuration.config_root))

        generate_keypair = click.confirm("Do you need to generate a new wallet to use for staking?")
        if generate_keypair:
            passphrase = click.prompt("Enter a passphrase to encrypt your wallet's private key")
            keyring = NucypherKeyring.generate(passphrase=passphrase,
                                               keyring_root=configuration.keyring_dir,
                                               encrypting=False,  # TODO: Set to True by default
                                               wallet=True)

        else:
            existing_wallet_path = click.prompt("Enter existing wallet.json path")
            keyring = NucypherKeyring.from_wallet_file(root_key_path=existing_wallet_path)  # TODO: classmethod and import

        generate_certificate = click.confirm("Do you need to generate a new SSL certificate?")
        if generate_certificate:

            days = click.prompt("How many days do you want the certificate to remain valid? (365 is default)",
                                default=365,
                                type=int)

            host = click.prompt("Enter the node's hostname", default='localhost')  # TODO: remove localhost as default

            # TODO: save TLS private key
            certificate, private_key = generate_self_signed_certificate(common_name=keyring.transacting_public_key,
                                                                        host=host,
                                                                        days_valid=days,
                                                                        curve=ec.SECP384R1)  # TODO: use Config class?

            certificate_filepath = os.path.join(configuration.known_certificates_dir, "{}.pem".format(keyring.transacting_public_key))
            _save_tls_certificate(certificate=certificate, full_filepath=certificate_filepath)

    if config.config_root:
        node_configuration = NodeConfiguration(temp=False,
                                               config_root=config.config_root,
                                               auto_initialize=False)
    elif config.dev:
        node_configuration = NodeConfiguration(temp=config.dev, auto_initialize=False)
    elif config.config_file:
        click.echo("Using configuration file at: {}".format(config.config_file))
        node_configuration = NodeConfiguration.from_configuration_file(filepath=config.config_file)
    else:
        node_configuration = NodeConfiguration(auto_initialize=False)  # Fully Default

    #
    # Action switch
    #
    if action == "init":
        __initialize(node_configuration)
    elif action == "destroy":
        __destroy(node_configuration)
    elif action == "reset":
        __destroy(node_configuration)
        __initialize(node_configuration)
    elif action == "validate":
        is_valid = True  # Until there is a reason to believe otherwise
        try:
            if filesystem:   # Check runtime directory
                is_valid = NodeConfiguration.check_config_tree_exists(config_root=node_configuration.config_root)
            if config.config_file:
                is_valid = validate_configuration_file(filepath=node_configuration.config_file_location)
        except NodeConfiguration.InvalidConfiguration:
            is_valid = False
        finally:
            result = 'Valid' if is_valid else 'Invalid'
            click.echo('{} is {}'.format(node_configuration.config_root, result))


@cli.command()
@click.option('--checksum-address', help="The account to lock/unlock instead of the default")
@click.argument('action', default='list', required=False)
@uses_config
def accounts(config, action, checksum_address):
    """Manage nucypher node accounts"""

    if not config.federated_only:
        config.connect_to_blockchain()

    def __collect_transfer_details(denomination: str):
        destination = click.prompt("Enter destination checksum_address")
        if not is_checksum_address(destination):
            click.echo("{} is not a valid checksum checksum_address".format(destination))
            raise click.Abort()
        amount = click.prompt("Enter amount of {} to transfer".format(denomination), type=int)
        return destination, amount

    config.connect_to_contracts()

    if action == 'new':
        pass  # TODO

    if action == 'set-default':
        pass  # TODO: Change etherbase

    elif action == 'export':
        keyring = NucypherKeyring(common_name=checksum_address)
        click.confirm("Export private key to keyring on node {}?".format(config.provider_uri), abort=True)
        passphrase = click.prompt("Enter passphrase", type=str)
        keyring._export(blockchain=config.blockchain, passphrase=passphrase)

    elif action == 'list':
        accounts = config.blockchain.interface.w3.eth.accounts
        for index, checksum_address in enumerate(accounts):
            token_balance = config.token_agent.get_balance(address=checksum_address)
            eth_balance = config.blockchain.interface.w3.eth.getBalance(checksum_address)
            if index == 0:
                row = 'etherbase | {} | Tokens: {} | ETH: {} '.format(checksum_address, token_balance, eth_balance)
            else:
                row = '{} ....... | {} | Tokens: {} | ETH: {}'.format(index, checksum_address, token_balance, eth_balance)
            click.echo(row)

    elif action == 'balance':

        if not checksum_address:
            checksum_address = config.blockchain.interface.w3.eth.accounts[0]
            click.echo('No checksum_address supplied, Using the default {}'.format(checksum_address))

        token_balance = config.token_agent.get_balance(address=checksum_address)
        eth_balance = config.token_agent.blockchain.interface.w3.eth.getBalance(checksum_address)
        click.echo("Balance of {} | Tokens: {} | ETH: {}".format(checksum_address, token_balance, eth_balance))

    elif action == "transfer-tokens":
        destination, amount = __collect_transfer_details(denomination='tokens')
        click.confirm("Are you sure you want to send {} tokens to {}?".format(amount, destination), abort=True)
        txhash = config.token_agent.transfer(amount=amount, target_address=destination, sender_address=checksum_address)
        config.blockchain.wait_for_receipt(txhash)
        click.echo("Sent {} tokens to {} | {}".format(amount, destination, txhash))

    elif action == "transfer-eth":
        destination, amount = __collect_transfer_details(denomination='ETH')
        tx = {'to': destination, 'from': checksum_address, 'value': amount}
        click.confirm("Are you sure you want to send {} tokens to {}?".format(tx['value'], tx['to']), abort=True)
        txhash = config.blockchain.interface.w3.eth.sendTransaction(tx)
        config.blockchain.wait_for_receipt(txhash)
        click.echo("Sent {} ETH to {} | {}".format(amount, destination, str(txhash)))


@cli.command()
@click.option('--checksum-address', help="Send rewarded tokens to a specific address, instead of the default.")
@click.option('--value', help="Stake value in the smallest denomination")
@click.option('--duration', help="Stake duration in periods")
@click.option('--index', help="A specific stake index to resume")
@click.argument('action', default='list', required=False)
@uses_config
def stake(config, action, checksum_address, index, value, duration):
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

    config.connect_to_blockchain()
    config.connect_to_contracts()

    if not checksum_address:

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
@click.option('--nodes', help="The number of nodes to simulate", type=int, default=10)
@click.argument('action')
@uses_config
def simulate(config, action, nodes):
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

        #
        # Blockchain Connection
        #

        if not config.federated_only:
            if config.provider_uri not in ("tester://geth", "tester://pyevm"):
                raise NotImplementedError

            simulation_registry = TemporaryEthereumContractRegistry()
            simulation_interface = BlockchainDeployerInterface(provider_uri=config.provider_uri,
                                                               registry=simulation_registry,
                                                               compiler=SolidityCompiler())

            blockchain = TesterBlockchain(interface=simulation_interface, test_accounts=nodes, airdrop=False)

            accounts = blockchain.interface.w3.eth.accounts
            origin, *everyone_else = accounts

            # Set the deployer address from the freshly created test account
            simulation_interface.deployer_address = origin

            #
            # Blockchain Action
            #
            blockchain.ether_airdrop(amount=DEVELOPMENT_ETH_AIRDROP_AMOUNT)

            click.confirm("Deploy all nucypher contracts to {}?".format(config.provider_uri), abort=True)
            click.echo("Bootstrapping simulated blockchain network")

            # Deploy contracts
            token_deployer = NucypherTokenDeployer(blockchain=blockchain, deployer_address=origin)
            token_deployer.arm()
            token_deployer.deploy()
            token_agent = token_deployer.make_agent()

            miners_escrow_secret = os.urandom(DISPATCHER_SECRET_LENGTH)
            miner_escrow_deployer = MinerEscrowDeployer(token_agent=token_agent,
                                                        deployer_address=origin,
                                                        secret_hash=miners_escrow_secret)
            miner_escrow_deployer.arm()
            miner_escrow_deployer.deploy()
            miner_agent = miner_escrow_deployer.make_agent()

            policy_manager_secret = os.urandom(DISPATCHER_SECRET_LENGTH)
            policy_manager_deployer = PolicyManagerDeployer(miner_agent=miner_agent,
                                                            deployer_address=origin,
                                                            secret_hash=policy_manager_secret)
            policy_manager_deployer.arm()
            policy_manager_deployer.deploy()
            policy_agent = policy_manager_deployer.make_agent()

            airdrop_amount = DEVELOPMENT_TOKEN_AIRDROP_AMOUNT
            click.echo("Airdropping tokens {} to {} addresses".format(airdrop_amount, len(everyone_else)))
            _receipts = token_airdrop(token_agent=token_agent,
                                      origin=origin,
                                      addresses=everyone_else,
                                      amount=airdrop_amount)

            # Commit the current state of deployment to a registry file.
            click.echo("Writing filesystem registry")
            _sim_registry_name = blockchain.interface.registry.commit(filepath=DEFAULT_SIMULATION_REGISTRY_FILEPATH)

        click.echo("Ready to run swarm.")

        #
        # Swarm
        #

        # Select a port range to use on localhost for sim servers

        if not config.federated_only:
            sim_addresses = everyone_else
        else:
            sim_addresses = NotImplemented

        start_port = 8787
        counter = 0
        for sim_port_number, sim_address in enumerate(sim_addresses, start=start_port):

            #
            # Parse ursula parameters
            #

            rest_port = sim_port_number
            db_name = 'sim-{}'.format(rest_port)

            cli_exec = os.path.join(BASE_DIR, 'cli', 'main.py')
            python_exec = 'python'

            proc_params = '''
            python3 {} run_ursula --rest-port {} --db-name {}
            '''.format(python_exec, cli_exec, rest_port, db_name).split()

            if config.federated_only:
                proc_params.append('--federated-only')

            else:
                token_agent = NucypherTokenAgent(blockchain=blockchain)
                miner_agent = MinerAgent(token_agent=token_agent)
                miner = Miner(miner_agent=miner_agent, checksum_address=sim_address)

                # stake a random amount
                min_stake, balance = MIN_ALLOWED_LOCKED, miner.token_balance
                value = random.randint(min_stake, balance)

                # for a random lock duration
                min_locktime, max_locktime = MIN_LOCKED_PERIODS, MAX_MINTING_PERIODS
                periods = random.randint(min_locktime, max_locktime)

                miner.initialize_stake(amount=value, lock_periods=periods)
                click.echo("{} Initialized new stake: {} tokens for {} periods".format(sim_address, value, periods))

                proc_params.extend('--checksum-address {}'.format(sim_address).split())

            # Spawn
            click.echo("Spawning node #{}".format(counter+1))
            processProtocol = UrsulaProcessProtocol(command=proc_params)
            cli_exec = os.path.join(BASE_DIR, 'cli', 'main.py')
            ursula_proc = reactor.spawnProcess(processProtocol, cli_exec, proc_params)

            #
            # post-spawnProcess
            #

            # Start with some basic status data, then build on it

            rest_uri = "http://{}:{}".format('localhost', rest_port)

            sim_data = "Started simulated Ursula | ReST {}".format(rest_uri)
            rest_uri = "{host}:{port}".format(host='localhost', port=str(sim_port_number))
            sim_data.format(rest_uri)

            # if not federated_only:
            #     stake_infos = tuple(config.miner_agent.get_all_stakes(miner_address=sim_address))
            #     sim_data += '| ETH address {}'.format(sim_address)
            #     sim_data += '| {} Active stakes '.format(len(stake_infos))

            click.echo(sim_data)
            counter += 1

        click.echo("Starting the reactor")
        click.confirm("Start the reactor?", abort=True)
        try:
            reactor.run()
        finally:

            if not config.federated_only:
                click.echo("Removing simulation registry")
                os.remove(DEFAULT_SIMULATION_REGISTRY_FILEPATH)

            click.echo("Stopping simulated Ursula processes")
            for process in config.sim_processes:
                os.kill(process.pid, 9)
                click.echo("Killed {}".format(process))

            click.echo("Simulation completed")

    elif action == 'stop':
        # Kill the simulated ursulas
        for process in config.ursula_processes:
            process.transport.signalProcess('KILL')

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
        
    """.format(registry_filepath=config.blockchain.interface.filepath,
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
@click.option('--dev', is_flag=True, default=False)
@click.option('--federated-only', is_flag=True)
@click.option('--poa', is_flag=True)
@click.option('--rest-host', type=str)
@click.option('--rest-port', type=int)
@click.option('--db-name', type=str)
@click.option('--provider-uri', type=str)
@click.option('--registry-filepath', type=click.Path())
@click.option('--checksum-address', type=str)
@click.option('--stake-amount', type=int)
@click.option('--stake-periods', type=int)
@click.option('--metadata-dir', type=click.Path())
@click.option('--config-file', type=click.Path())
def run_ursula(rest_port,
               rest_host,
               db_name,
               provider_uri,
               registry_filepath,
               checksum_address,
               stake_amount,
               stake_periods,
               federated_only,
               metadata_dir,
               config_file,
               poa,
               dev
               ) -> None:
    """

    The following procedure is required to "spin-up" an Ursula node.

        1. Initialize UrsulaConfiguration
        2. Initialize Ursula
        3. Run TLS deployment
        4. Start the staking daemon

    Configurable values are first read from the configuration file,
    but can be overridden (mostly for testing purposes) with inline cli options.

    """
    if not dev:
        click.echo("WARNING: Development mode is disabled")
        temp = False
    else:
        click.echo("Running in development mode")
        temp = True

    if config_file:
        ursula_config = UrsulaConfiguration.from_configuration_file(filepath=config_file)
    else:
        ursula_config = UrsulaConfiguration(temp=temp,
                                            auto_initialize=temp,
                                            poa=poa,
                                            rest_host=rest_host,
                                            rest_port=rest_port,
                                            db_name=db_name,
                                            is_me=True,
                                            federated_only=federated_only,
                                            registry_filepath=registry_filepath,
                                            provider_uri=provider_uri,
                                            checksum_address=checksum_address,
                                            # save_metadata=False,  # TODO
                                            load_metadata=True,
                                            known_metadata_dir=metadata_dir,
                                            start_learning_now=True,
                                            abort_on_learning_error=temp)

    passphrase = click.prompt("Enter passphrase to unlock account", type=str)
    try:

        URSULA = ursula_config.produce(passphrase=passphrase)

        if not federated_only:

            URSULA.stake(amount=stake_amount, lock_periods=stake_periods)

        URSULA.get_deployer().run()       # Run TLS Deploy (Reactor)

    finally:

        click.echo("Cleaning up temporary runtime files and directories")
        ursula_config.cleanup()  # TODO: Integrate with other "graceful" shutdown functionality
        click.echo("Exited gracefully")


if __name__ == "__main__":
    cli()
