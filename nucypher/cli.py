#!/usr/bin/env python3


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
import os
import shutil
import socket
from ipaddress import ip_address
from typing import Tuple, ClassVar
from urllib.parse import urlparse

import click
import requests
import time
from constant_sorrow.constants import NO_NODE_CONFIGURATION, NO_BLOCKCHAIN_CONNECTION
from eth_utils import is_checksum_address
from nacl.exceptions import CryptoError
from sentry_sdk.integrations.logging import LoggingIntegration
from twisted.internet import stdio
from twisted.logger import Logger
from twisted.logger import globalLogPublisher
from web3.middleware import geth_poa_middleware

import nucypher
from nucypher.blockchain.eth.agents import MinerAgent, PolicyAgent, NucypherTokenAgent, EthereumContractAgent
from nucypher.blockchain.eth.chains import Blockchain
from nucypher.blockchain.eth.constants import (MIN_ALLOWED_LOCKED,
                                               MIN_LOCKED_PERIODS,
                                               MAX_MINTING_PERIODS)
from nucypher.blockchain.eth.deployers import (NucypherTokenDeployer,
                                               MinerEscrowDeployer,
                                               PolicyManagerDeployer)
from nucypher.characters.lawful import Ursula
from nucypher.config.characters import UrsulaConfiguration
from nucypher.config.constants import SEEDNODES
from nucypher.config.keyring import NucypherKeyring
from nucypher.config.node import NodeConfiguration
from nucypher.utilities.logging import logToSentry
from nucypher.utilities.sandbox.ursula import UrsulaCommandProtocol

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

""".format(nucypher.__version__)


class NucypherClickConfig:
    __LOG_TO_SENTRY_ENVVAR = "NUCYPHER_SENTRY_LOGS"
    __NUCYPHER_SENTRY_ENDPOINT = "https://d8af7c4d692e4692a455328a280d845e@sentry.io/1310685"
    _KEYRING_PASSPHRASE_ENVVAR = "NUCYPHER_KEYRING_PASSPHRASE"

    # Set to False to completely opt-out of sentry reporting
    log_to_sentry = os.environ.get(__LOG_TO_SENTRY_ENVVAR, True)

    # Pending Configuration Named Tuple
    PendingConfigurationDetails = collections.namedtuple('PendingConfigurationDetails',
                                                         'passphrase wallet signing tls skip_keys save_file')

    def __init__(self):
        if self.log_to_sentry:
            import sentry_sdk
            import logging
            sentry_logging = LoggingIntegration(
                level=logging.INFO,  # Capture info and above as breadcrumbs
                event_level=logging.DEBUG  # Send debug logs as events
            )
            sentry_sdk.init(
                dsn=self.__NUCYPHER_SENTRY_ENDPOINT,
                integrations=[sentry_logging],
                release=nucypher.__version__
            )

            globalLogPublisher.addObserver(logToSentry)

        self.log = Logger(self.__class__.__name__)

        # Node Configuration
        self.node_configuration = NO_NODE_CONFIGURATION
        self.dev = NO_NODE_CONFIGURATION
        self.federated_only = NO_NODE_CONFIGURATION
        self.config_root = NO_NODE_CONFIGURATION
        self.config_file = NO_NODE_CONFIGURATION

        # Blockchain
        self.deployer = NO_BLOCKCHAIN_CONNECTION
        self.compile = NO_BLOCKCHAIN_CONNECTION
        self.poa = NO_BLOCKCHAIN_CONNECTION
        self.blockchain = NO_BLOCKCHAIN_CONNECTION
        self.provider_uri = NO_BLOCKCHAIN_CONNECTION
        self.registry_filepath = NO_BLOCKCHAIN_CONNECTION
        self.accounts = NO_BLOCKCHAIN_CONNECTION

        # Agency
        self.token_agent = NO_BLOCKCHAIN_CONNECTION
        self.miner_agent = NO_BLOCKCHAIN_CONNECTION
        self.policy_agent = NO_BLOCKCHAIN_CONNECTION

    def get_node_configuration(self, configuration_class=UrsulaConfiguration, **overrides):
        if self.dev:
            node_configuration = configuration_class(temp=self.dev, auto_initialize=False,
                                                     federated_only=self.federated_only)
        else:
            try:
                filepath = self.config_file or UrsulaConfiguration.DEFAULT_CONFIG_FILE_LOCATION
                node_configuration = configuration_class.from_configuration_file(filepath=filepath)
            except FileNotFoundError:
                if self.config_root:
                    node_configuration = configuration_class(temp=False, config_root=self.config_root,
                                                             auto_initialize=False)
                else:
                    node_configuration = configuration_class(federated_only=self.federated_only,
                                                             auto_initialize=False,
                                                             **overrides)
            else:
                click.secho("Reading Ursula node configuration file {}".format(filepath), fg='blue')

        self.node_configuration = node_configuration

    def connect_to_blockchain(self):
        if self.federated_only:
            raise NodeConfiguration.ConfigurationError("Cannot connect to blockchain in federated mode")
        if self.deployer:
            self.registry_filepath = NodeConfiguration.REGISTRY_SOURCE
        if self.compile:
            click.confirm("Compile solidity source?", abort=True)
        self.blockchain = Blockchain.connect(provider_uri=self.provider_uri,
                                             deployer=self.deployer,
                                             compile=self.compile)
        if self.poa:
            w3 = self.blockchain.interface.w3
            w3.middleware_stack.inject(geth_poa_middleware, layer=0)
        self.accounts = self.blockchain.interface.w3.eth.accounts
        self.log.debug("CLI established connection to provider {}".format(self.blockchain.interface.provider_uri))

    def connect_to_contracts(self) -> None:
        """Initialize contract agency and set them on config"""
        self.token_agent = NucypherTokenAgent(blockchain=self.blockchain)
        self.miner_agent = MinerAgent(blockchain=self.blockchain)
        self.policy_agent = PolicyAgent(blockchain=self.blockchain)
        self.log.debug("CLI established connection to nucypher contracts")

    def create_account(self, passphrase: str = None) -> str:
        """Creates a new local or hosted ethereum wallet"""
        choice = click.prompt("Create a new Hosted or Local account?", default='hosted',
                              type=click.STRING).strip().lower()
        if choice not in ('hosted', 'local'):
            click.echo("Invalid Input")
            raise click.Abort()

        if not passphrase:
            message = "Enter a passphrase to encrypt your wallet's private key"
            passphrase = click.prompt(message, hide_input=True, confirmation_prompt=True)

        if choice == 'local':
            keyring = NucypherKeyring.generate(passphrase=passphrase,
                                               keyring_root=self.node_configuration.keyring_dir,
                                               encrypting=False,
                                               wallet=True)
            new_address = keyring.checksum_address
        elif choice == 'hosted':
            new_address = self.blockchain.interface.w3.personal.newAccount(passphrase)
        else:
            raise click.BadParameter("Invalid choice; Options are hosted or local.")
        return new_address

    def _collect_pending_configuration_details(self, ursula: bool = False, force: bool = False,
                                               rest_host=None) -> PendingConfigurationDetails:

        # Defaults
        passphrase = None
        skip_all_key_generation, generate_wallet = False, False
        generate_encrypting_keys, generate_tls_keys, save_node_configuration_file = True, True, True

        if ursula:
            if not self.federated_only:  # Wallet
                generate_wallet = click.confirm("Do you need to generate a new wallet to use for staking?",
                                                default=False)

                if not generate_wallet:  # I'll take that as a no...
                    self.federated_only = True  # TODO: Without a wallet...
                    #  let's understand this to be a "federated configuration"

            if generate_tls_keys or force:
                if not force and not rest_host:
                    rest_host = click.prompt("Enter Node's Public IPv4 Address", type=IPV4_ADDRESS)

                self.node_configuration.rest_host = rest_host

        if not force:  # Signing / Encrypting
            if not any((generate_wallet, generate_tls_keys, generate_encrypting_keys)):
                skip_all_key_generation = click.confirm("Skip all key generation (Provide custom configuration file)?")

        if not skip_all_key_generation:
            if os.environ.get(self._KEYRING_PASSPHRASE_ENVVAR):
                passphrase = os.environ.get(self._KEYRING_PASSPHRASE_ENVVAR)
            else:
                passphrase = click.prompt("Enter a passphrase to encrypt your keyring",
                                          hide_input=True, confirmation_prompt=True)

        details = self.PendingConfigurationDetails(passphrase=passphrase, wallet=generate_wallet,
                                                   signing=generate_encrypting_keys, tls=generate_tls_keys,
                                                   skip_keys=skip_all_key_generation,
                                                   save_file=save_node_configuration_file)
        return details

    def create_new_configuration(self,
                                 ursula: bool = False,
                                 force: bool = False,
                                 rest_host: str = None,
                                 no_registry: bool = False):

        if force:
            click.secho("Force is enabled - Using defaults", fg='yellow')
        if self.dev:
            click.secho("Using temporary storage area", fg='blue')

        if not no_registry and not self.federated_only:
            registry_source = self.node_configuration.REGISTRY_SOURCE
            if not os.path.isfile(registry_source):
                click.echo("Seed contract registry does not exist at path {}.  "
                           "Use --no-registry to skip.".format(registry_source))
                raise click.Abort()

        if self.config_root:  # Custom installation location
            self.node_configuration.config_root = self.config_root
        self.node_configuration.federated_only = self.federated_only

        try:
            pending_config = self._collect_pending_configuration_details(force=force, ursula=ursula,
                                                                         rest_host=rest_host)
            new_installation_path = self.node_configuration.initialize(passphrase=pending_config.passphrase,
                                                                       wallet=pending_config.wallet,
                                                                       encrypting=pending_config.signing,
                                                                       tls=pending_config.tls,
                                                                       no_registry=no_registry,
                                                                       no_keys=pending_config.skip_keys,
                                                                       host=rest_host)
            if not pending_config.skip_keys:
                click.secho("Generated new keys at {}".format(self.node_configuration.keyring_dir), fg='blue')
        except NodeConfiguration.ConfigurationError as e:
            click.secho(str(e), fg='red')
            raise click.Abort()
        else:
            click.secho("Created nucypher installation files at {}".format(new_installation_path), fg='green')
            if pending_config.save_file is True:
                configuration_filepath = self.node_configuration.to_configuration_file(filepath=self.config_file)
                click.secho("Saved node configuration file {}".format(configuration_filepath), fg='green')
                if ursula:
                    click.secho("\nTo run an Ursula node from the "
                                "default configuration filepath run 'nucypher ursula run'\n")

    def forget_nodes(self) -> None:

        def __destroy_dir_contents(path):
            for file in os.listdir(path):
                file_path = os.path.join(path, file)
                if os.path.isfile(file_path):
                    os.unlink(file_path)

        click.confirm("Remove all known node data?", abort=True)
        certificates_dir = self.node_configuration.known_certificates_dir
        metadata_dir = os.path.join(self.node_configuration.known_nodes_dir, 'metadata')

        __destroy_dir_contents(certificates_dir)
        __destroy_dir_contents(metadata_dir)
        click.secho("Removed all stored node node metadata and certificates")

    def destroy_configuration(self) -> None:
        if self.dev:
            raise NodeConfiguration.ConfigurationError("Cannot destroy a temporary node configuration")
        click.confirm('''
*Permanently and irreversibly delete all* nucypher files including:
  - Private and Public Keys
  - Known Nodes
  - TLS certificates
  - Node Configurations
Located at {}?'''.format(self.node_configuration.config_root), abort=True)
        shutil.rmtree(self.node_configuration.config_root, ignore_errors=True)
        click.secho("Deleted configuration files at {}".format(self.node_configuration.config_root), fg='blue')


#########################################

# Register the above class as a decorator
uses_config = click.make_pass_decorator(NucypherClickConfig, ensure=True)


#
# Click Eager Functions
#

def echo_version(ctx, param, value):
    if not value or ctx.resilient_parsing:
        return
    click.secho(BANNER, bold=True)
    ctx.exit()


#
# Custom Click Input Types
#

class ChecksumAddress(click.ParamType):
    name = 'checksum_address'

    def convert(self, value, param, ctx):
        if is_checksum_address(value):
            return value
        self.fail('{} is not a valid EIP-55 checksum address'.format(value, param, ctx))


class IPv4Address(click.ParamType):
    name = 'ipv4_address'

    def convert(self, value, param, ctx):
        try:
            _address = ip_address(value)
        except ValueError as e:
            self.fail(str(e))
        else:
            return value


IPV4_ADDRESS = IPv4Address()
CHECKSUM_ADDRESS = ChecksumAddress()


########################################


#
# CLI Commands
#

@click.group()
@click.option('--version', help="Echo the CLI version", is_flag=True, callback=echo_version, expose_value=False,
              is_eager=True)
@click.option('-v', '--verbose', help="Specify verbosity level", count=True)
@click.option('--dev', help="Run in development mode", is_flag=True)
@click.option('--federated-only', help="Connect only to federated nodes", is_flag=True, default=True)
@click.option('--config-root', help="Custom configuration directory", type=click.Path())
@click.option('--config-file', help="Path to configuration file",
              type=click.Path(exists=True, dir_okay=False, file_okay=True, readable=True))
@click.option('--metadata-dir', help="Custom known metadata directory",
              type=click.Path(exists=True, dir_okay=True, file_okay=False, writable=True))
@click.option('--provider-uri', help="Blockchain provider's URI", type=click.STRING)
@click.option('--compile/--no-compile', help="Compile solidity from source files", is_flag=True)
@click.option('--registry-filepath', help="Custom contract registry filepath",
              type=click.Path(exists=True, dir_okay=False, file_okay=True, readable=True))
@click.option('--deployer', help="Connect using a deployer's blockchain interface", is_flag=True)
@click.option('--poa', help="Inject POA middleware", is_flag=True)
@uses_config
def cli(config,
        verbose,
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

    # CLI Node View
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

    if config.verbose:
        click.secho("Verbose mode is enabled", fg='blue')

    if not config.dev:
        click.secho("WARNING: Development mode is disabled", fg='yellow', bold=True)
    else:
        click.secho("Running in development mode", fg='blue')


@cli.command()
@click.option('--rest-host', type=click.STRING)
@click.option('--no-registry', help="Skip importing the default contract registry", is_flag=True)
@click.option('--force', help="Ask confirm once; Do not generate wallet or certificate", is_flag=True)
@click.argument('action')
@uses_config
def configure(config,
              action,
              rest_host,
              no_registry,
              force):
    """Manage Ursula node system configuration


Actions:

install     Create a new Ursula node configuration
view        View the configuration of Ursula node
forget      Remove all stored known nodes' metadata and certificates
reset       Delete current Ursula node configuration and create a new one
destroy     Delete current Ursula node configuration
    """

    # Fetch Existing Configuration
    config.get_node_configuration(configuration_class=UrsulaConfiguration, rest_host=rest_host)

    if action == "destroy":
        config.destroy_configuration()

    elif action == "install":
        config.create_new_configuration(ursula=ursula, force=force, no_registry=no_registry, rest_host=rest_host)

    elif action == "view":
        config_filepath = config.node_configuration.config_file_location
        json_config = UrsulaConfiguration._read_configuration_file(filepath=config_filepath)

        click.secho("\n======== Ursula Configuration ======== \n", bold=True)
        for key, value in json_config.items():
            click.secho("{} = {}".format(key, value))

    elif action == "forget":
        config.forget_nodes()

    elif action == "reset":
        config.destroy_configuration()
        config.create_new_configuration(ursula=True, force=force, no_registry=no_registry, rest_host=rest_host)

    else:
        raise click.BadArgumentUsage("No such argument {}".format(action))


@cli.command()
@click.option('--checksum-address', help="The account to lock/unlock instead of the default", type=CHECKSUM_ADDRESS)
@click.argument('action', default='list', required=False)
@uses_config
def accounts(config,
             action,
             checksum_address):
    """Manage local and hosted node accounts"""

    #
    # Initialize
    #
    config.get_node_configuration()
    if not config.federated_only:
        config.connect_to_blockchain()
        config.connect_to_contracts()

        if not checksum_address:
            checksum_address = config.blockchain.interface.w3.eth.coinbase
            click.echo("WARNING: No checksum address specified - Using the node's default account.")

    def __collect_transfer_details(denomination: str):
        destination = click.prompt("Enter destination checksum_address")
        if not is_checksum_address(destination):
            click.secho("{} is not a valid checksum checksum_address".format(destination), fg='red', bold=True)
            raise click.Abort()
        amount = click.prompt("Enter amount of {} to transfer".format(denomination), type=click.INT)
        return destination, amount

    #
    # Action Switch
    #
    if action == 'new':
        new_address = config.create_account()
        click.secho("Created new ETH address {}".format(new_address), fg='blue')
        if click.confirm("Set new address as the node's keying default account?".format(new_address)):
            config.blockchain.interface.w3.eth.defaultAccount = new_address
            click.echo(
                "{} is now the node's default account.".format(config.blockchain.interface.w3.eth.defaultAccount))

    if action == 'set-default':
        config.blockchain.interface.w3.eth.defaultAccount = checksum_address  # TODO: is there a better way to do this?
        click.echo("{} is now the node's default account.".format(config.blockchain.interface.w3.eth.defaultAccount))

    elif action == 'export':
        keyring = NucypherKeyring(account=checksum_address)
        click.confirm(
            "Export local private key for {} to node's keyring: {}?".format(checksum_address, config.provider_uri),
            abort=True)
        passphrase = click.prompt("Enter passphrase to decrypt account", type=click.STRING, hide_input=True,
                                  confirmation_prompt=True)
        keyring._export_wallet_to_node(blockchain=config.blockchain, passphrase=passphrase)

    elif action == 'list':
        if config.accounts == NO_BLOCKCHAIN_CONNECTION:
            click.echo('No account found.')
            return

        for index, checksum_address in enumerate(config.accounts):
            token_balance = config.token_agent.get_balance(address=checksum_address)
            eth_balance = config.blockchain.interface.w3.eth.getBalance(checksum_address)
            base_row_template = ' {address}\n    Tokens: {tokens}\n    ETH: {eth}\n '
            row_template = (
                        '\netherbase |' + base_row_template) if not index else '{index} ....... |' + base_row_template
            row = row_template.format(index=index, address=checksum_address, tokens=token_balance, eth=eth_balance)
            click.secho(row, fg='blue')

    elif action == 'balance':
        if not checksum_address:
            checksum_address = config.blockchain.interface.w3.eth.etherbase
            click.echo('No checksum_address supplied, Using the default {}'.format(checksum_address))
        token_balance = config.token_agent.get_balance(address=checksum_address)
        eth_balance = config.token_agent.blockchain.interface.w3.eth.getBalance(checksum_address)
        click.secho("Balance of {} | Tokens: {} | ETH: {}".format(checksum_address, token_balance, eth_balance),
                    fg='blue')

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

    else:
        raise click.BadArgumentUsage


@cli.command()
@click.option('--checksum-address', type=CHECKSUM_ADDRESS)
@click.option('--value', help="Token value of stake",
              type=click.IntRange(min=MIN_ALLOWED_LOCKED, max=MIN_ALLOWED_LOCKED, clamp=False))
@click.option('--duration', help="Period duration of stake",
              type=click.IntRange(min=MIN_LOCKED_PERIODS, max=MAX_MINTING_PERIODS, clamp=False))
@click.option('--index', help="A specific stake index to resume", type=click.INT)
@click.argument('action', default='list', required=False)
@uses_config
def stake(config,
          action,
          checksum_address,
          index,
          value,
          duration):
    """
    Manage token staking.


Actions:

    action - Which action to perform; The choices are:
list              List all stakes for this node
init              Stage a new stake
start             Start the staking daemon
confirm-activity  Manually confirm-activity for the current period
divide            Divide an existing stake
collect-reward    Withdraw staking reward

    """

    #
    # Initialize
    #
    config.get_node_configuration()
    if not config.federated_only:
        config.connect_to_blockchain()
        config.connect_to_contracts()

    if not checksum_address:

        if config.accounts == NO_BLOCKCHAIN_CONNECTION:
            click.echo('No account found.')
            return

        for index, address in enumerate(config.accounts):
            if index == 0:
                row = 'etherbase (0) | {}'.format(address)
            else:
                row = '{} .......... | {}'.format(index, address)
            click.echo(row)

        click.echo("Select ethereum address")
        account_selection = click.prompt("Enter 0-{}".format(len(config.accounts)), type=click.INT)
        address = config.accounts[account_selection]

    if action == 'list':
        live_stakes = config.miner_agent.get_all_stakes(miner_address=checksum_address)
        for index, stake_info in enumerate(live_stakes):
            row = '{} | {}'.format(index, stake_info)
            click.echo(row)

    elif action == 'init':
        click.confirm("Stage a new stake?", abort=True)

        live_stakes = config.miner_agent.get_all_stakes(miner_address=checksum_address)
        if len(live_stakes) > 0:
            raise RuntimeError("There is an existing stake for {}".format(checksum_address))

        # Value
        balance = config.token_agent.get_balance(address=checksum_address)
        click.echo("Current balance: {}".format(balance))
        value = click.prompt("Enter stake value", type=click.INT)

        # Duration
        message = "Minimum duration: {} | Maximum Duration: {}".format(MIN_LOCKED_PERIODS,
                                                                       MAX_MINTING_PERIODS)
        click.echo(message)
        duration = click.prompt("Enter stake duration in periods (1 Period = 24 Hours)", type=click.INT)

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
        
        """.format(address=checksum_address,
                   value=value,
                   duration=duration,
                   start_period=start_period,
                   end_period=end_period))

        # TODO: Ursula Process management
        raise NotImplementedError

    elif action == 'confirm-activity':
        """Manually confirm activity for the active period"""
        stakes = config.miner_agent.get_all_stakes(miner_address=checksum_address)
        if len(stakes) == 0:
            raise RuntimeError("There are no active stakes for {}".format(checksum_address))
        config.miner_agent.confirm_activity(node_address=checksum_address)

    elif action == 'divide':
        """Divide an existing stake by specifying the new target value and end period"""

        stakes = config.miner_agent.get_all_stakes(miner_address=checksum_address)
        if len(stakes) == 0:
            raise RuntimeError("There are no active stakes for {}".format(checksum_address))

        if not index:
            for selection_index, stake_info in enumerate(stakes):
                click.echo("{} ....... {}".format(selection_index, stake_info))
            index = click.prompt("Select a stake to divide", type=click.INT)

        target_value = click.prompt("Enter new target value", type=click.INT)
        extension = click.prompt("Enter number of periods to extend", type=click.INT)

        click.echo("""
        Current Stake: {}
        
        New target value {}
        New end period: {}
        
        """.format(stakes[index],
                   target_value,
                   target_value + extension))

        click.confirm("Is this correct?", abort=True)
        config.miner_agent.divide_stake(miner_address=checksum_address,
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

    else:
        raise click.BadArgumentUsage


@cli.command()
@click.option('--contract-name', help="Deploy a single contract by name", type=click.STRING)
@click.option('--force', is_flag=True)
@click.option('--deployer-address', help="Deployer's checksum address", type=CHECKSUM_ADDRESS)
@click.option('--registry-outfile', help="Output path for new registry", type=click.Path(),
              default=NodeConfiguration.REGISTRY_SOURCE)
@click.argument('action')
@uses_config
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

        DeployerInfo = collections.namedtuple('DeployerInfo', 'deployer_class upgradeable agent_name dependant')
        deployers = collections.OrderedDict({

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
                                                               dependant='miner_agent'
                                                               )
        })

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
            file.write(json.dumps(__deployment_transactions))
            click.secho("Successfully wrote transaction hashes file to {}".format(file.path), fg='green')

    else:
        raise click.BadArgumentUsage


@cli.command()
@uses_config
def status(config):
    """
    Echo a snapshot of live network metadata.
    """
    #
    # Initialize
    #
    config.get_node_configuration()
    if not config.node_configuration.federated_only:
        config.connect_to_blockchain()
        config.connect_to_contracts()

        contract_payload = """
        
        | NuCypher ETH Contracts |
        
        Provider URI ............. {provider_uri}
        Registry Path ............ {registry_filepath}
    
        NucypherToken ............ {token}
        MinerEscrow .............. {escrow}
        PolicyManager ............ {manager}
            
        """.format(provider_uri=config.blockchain.interface.provider_uri,
                   registry_filepath=config.blockchain.interface.registry.filepath,
                   token=config.token_agent.contract_address,
                   escrow=config.miner_agent.contract_address,
                   manager=config.policy_agent.contract_address,
                   period=config.miner_agent.get_current_period())
        click.secho(contract_payload)

        network_payload = """
        | Blockchain Network |
        
        Current Period ........... {period}
        Gas Price ................ {gas_price}
        Active Staking Ursulas ... {ursulas}
        
        """.format(period=config.miner_agent.get_current_period(),
                   gas_price=config.blockchain.interface.w3.eth.gasPrice,
                   ursulas=config.miner_agent.get_miner_population())
        click.secho(network_payload)

    #
    # Known Nodes
    #

    # Gather Data
    known_nodes = config.node_configuration.read_known_nodes()
    known_certificate_files = os.listdir(config.node_configuration.known_certificates_dir)
    number_of_known_nodes = len(known_nodes)
    seen_nodes = len(known_certificate_files)

    # Operating Mode
    federated_only = config.node_configuration.federated_only
    if federated_only:
        click.secho("Configured in Federated Only mode", fg='green')

    # Heading
    label = "Known Nodes (connected {} / seen {})".format(number_of_known_nodes, seen_nodes)
    heading = '\n' + label + " " * (45 - len(label)) + "Last Seen    "
    click.secho(heading, bold=True, nl=False)

    # Legend
    color_index = {
        'self': 'yellow',
        'known': 'white',
        'seednode': 'blue'
    }
    for node_type, color in color_index.items():
        click.secho('{0:<6} | '.format(node_type), fg=color, nl=False)
    click.echo('\n')

    seednode_addresses = list(bn.checksum_address for bn in SEEDNODES)
    for node in known_nodes:
        row_template = "{} | {} | {}"
        node_type = 'known'
        if node.checksum_public_address == config.node_configuration.checksum_address:
            node_type = 'self'
            row_template += ' ({})'.format(node_type)
        if node.checksum_public_address in seednode_addresses:
            node_type = 'seednode'
            row_template += ' ({})'.format(node_type)
        click.secho(row_template.format(node.checksum_public_address,
                                        node.rest_url(),
                                        node.timestamp), fg=color_index[node_type])


@cli.command()
@click.option('--debug', is_flag=True)
@click.option('--teacher-uri', type=click.STRING)
@click.option('--min-stake', type=click.INT, default=0)
@click.option('--rest-host', type=click.STRING)
@click.option('--rest-port', type=click.IntRange(min=49151, max=65535, clamp=False))
@click.option('--db-name', type=click.STRING)
@click.option('--checksum-address', type=CHECKSUM_ADDRESS)
@click.argument('action')
@uses_config
def ursula(config,
           action,
           rest_port,
           rest_host,
           db_name,
           checksum_address,
           debug,
           teacher_uri,
           min_stake
           ) -> None:
    """
    Manage and run an Ursula node

    Here is the procedure to "spin-up" an Ursula node.

        0. Validate CLI Input
        1. Initialize UrsulaConfiguration (from configuration file or inline)
        2. Initialize Ursula with Passphrase
        3. Initialize Staking Loop
        4. Run TLS deployment (Learning Loop + Reactor)

    """
    log = Logger("ursula/launch")

    password = os.environ.get(config._KEYRING_PASSPHRASE_ENVVAR, None)
    if not password:
        password = click.prompt("Password to unlock Ursula's keyring", hide_input=True)

    def __make_ursula():
        if not checksum_address and not config.dev:
            raise click.BadArgumentUsage("No Configuration file found, and no --checksum address <addr> was provided.")
        if not checksum_address and not config.dev:
            raise click.BadOptionUsage(message="No account specified. pass --checksum-address, --dev, "
                                               "or use a configuration file with --config-file <path>")

        return UrsulaConfiguration(temp=config.dev,
                                   auto_initialize=config.dev,
                                   is_me=True,
                                   rest_host=rest_host,
                                   rest_port=rest_port,
                                   db_name=db_name,
                                   federated_only=config.federated_only,
                                   registry_filepath=config.registry_filepath,
                                   provider_uri=config.provider_uri,
                                   checksum_address=checksum_address,
                                   poa=config.poa,
                                   save_metadata=False,
                                   load_metadata=True,
                                   start_learning_now=True,
                                   learn_on_same_thread=False,
                                   abort_on_learning_error=config.dev)

    #
    # Configure
    #
    overrides = dict()
    if config.dev:
        ursula_config = __make_ursula()
    else:
        try:
            filepath = config.config_file or UrsulaConfiguration.DEFAULT_CONFIG_FILE_LOCATION
            click.secho("Reading Ursula node configuration file {}".format(filepath), fg='blue')
            ursula_config = UrsulaConfiguration.from_configuration_file(filepath=filepath)
        except FileNotFoundError:
            ursula_config = __make_ursula()

    config.operating_mode = "federated" if ursula_config.federated_only else "decentralized"
    click.secho("Running in {} mode".format(config.operating_mode), fg='blue')

    #
    # Seed
    #
    teacher_nodes = list()
    if teacher_uri:

        if '@' in teacher_uri:
            checksum_address, teacher_uri = teacher_uri.split("@")
            if not is_checksum_address(checksum_address):
                raise click.BadParameter("{} is not a valid checksum address.".format(checksum_address))
        else:
            checksum_address = None  # federated

        # HTTPS Explicit Required
        parsed_teacher_uri = urlparse(teacher_uri)
        if not parsed_teacher_uri.scheme == "https":
            raise click.BadParameter("Invalid teacher URI. Is the hostname prefixed with 'https://' ?")

        port = parsed_teacher_uri.port or UrsulaConfiguration.DEFAULT_REST_PORT
        while not teacher_nodes:
            try:
                teacher = Ursula.from_seed_and_stake_info(host=parsed_teacher_uri.hostname,
                                                          port=port,
                                                          federated_only=ursula_config.federated_only,
                                                          checksum_address=checksum_address,
                                                          minimum_stake=min_stake,
                                                          certificates_directory=ursula_config.known_certificates_dir)
                teacher_nodes.append(teacher)
            except (socket.gaierror, requests.exceptions.ConnectionError, ConnectionRefusedError):
                log.warn("Can't connect to seed node.  Will retry.")
                time.sleep(5)

    #
    # Produce
    #
    try:
        URSULA = ursula_config.produce(passphrase=password,
                                       known_nodes=teacher_nodes,
                                       **overrides)  # 2
    except CryptoError:
        click.secho("Invalid keyring passphrase")
        return

    click.secho("Initialized Ursula {}".format(URSULA), fg='green')

    #
    # Run
    #
    if action == 'run':
        try:

            # GO!
            click.secho("Running Ursula on {}".format(URSULA.rest_interface), fg='green', bold=True)
            stdio.StandardIO(UrsulaCommandProtocol(ursula=URSULA))
            URSULA.get_deployer().run()

        except Exception as e:
            config.log.critical(str(e))
            click.secho("{} {}".format(e.__class__.__name__, str(e)), fg='red')
            if debug: raise
            raise click.Abort()
        finally:
            click.secho("Stopping Ursula")
            ursula_config.cleanup()
            click.secho("Ursula Stopped", fg='red')

    elif action == "save-metadata":
        metadata_path = URSULA.write_node_metadata(node=URSULA)
        click.secho("Successfully saved node metadata to {}.".format(metadata_path), fg='green')

    else:
        raise click.BadArgumentUsage


if __name__ == "__main__":
    cli()
