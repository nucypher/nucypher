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

import os

import click
import collections
from nacl.exceptions import CryptoError
from twisted.internet import stdio
from twisted.logger import Logger
from twisted.logger import globalLogPublisher

from constant_sorrow.constants import NO_BLOCKCHAIN_CONNECTION, NO_ENVVAR
from nucypher.blockchain.eth.constants import (MIN_ALLOWED_LOCKED,
                                               MIN_LOCKED_PERIODS,
                                               MAX_MINTING_PERIODS)
from nucypher.cli.constants import BANNER, LOG_TO_SENTRY, LOG_TO_FILE, KEYRING_PASSWORD_ENVVAR
from nucypher.cli.painting import paint_configuration
from nucypher.cli.protocol import UrsulaCommandProtocol
from nucypher.cli.types import IPV4_ADDRESS, CHECKSUM_ADDRESS
from nucypher.config.characters import UrsulaConfiguration
from nucypher.config.constants import SEEDNODES
from nucypher.network.nodes import Teacher
from nucypher.utilities.logging import (
    logToSentry,
    getTextFileObserver,
    initialize_sentry,
    getJsonFileObserver,
    SimpleObserver)


#
# Logging
#

# Sentry
if LOG_TO_SENTRY is True:
    initialize_sentry()
    globalLogPublisher.addObserver(logToSentry)

# Files
if LOG_TO_FILE is True:
    globalLogPublisher.addObserver(getTextFileObserver())
    globalLogPublisher.addObserver(getJsonFileObserver())


#
# Utilities
#


#
# Click Eager Functions
#

def echo_version(ctx, param, value):
    if not value or ctx.resilient_parsing:
        return
    click.secho(BANNER, bold=True)
    ctx.exit()


PendingConfigurationDetails = collections.namedtuple('PendingConfigurationDetails',
                                                     ('rest_host',    # type: str
                                                      'password',     # type: str
                                                      'wallet',       # type: bool
                                                      'signing',      # type: bool
                                                      'tls',          # type: bool
                                                      'skip_keys',    # type: bool
                                                      'save_file'))   # type: bool


def _collect_pending_configuration_details(ursula: bool = True, rest_host=None) -> PendingConfigurationDetails:

    # Defaults
    generate_wallet = False
    generate_encrypting_keys, generate_tls_keys, save_node_configuration_file = True, True, True

    if ursula and not rest_host:
        rest_host = click.prompt("Enter Node's Public IPv4 Address", type=IPV4_ADDRESS)

    if os.environ.get(KEYRING_PASSWORD_ENVVAR):
        password = os.environ.get(KEYRING_PASSWORD_ENVVAR)
    else:
        password = click.prompt("Enter a password to encrypt your keyring",
                                hide_input=True,
                                confirmation_prompt=True)

    details = PendingConfigurationDetails(password=password,
                                          rest_host=rest_host,
                                          wallet=generate_wallet,
                                          signing=generate_encrypting_keys,
                                          tls=generate_tls_keys,
                                          save_file=save_node_configuration_file,
                                          skip_keys=False)
    return details


#
# Click CLI Config
#

class NucypherClickConfig:
    def __init__(self):
        self.log = Logger(self.__class__.__name__)


uses_config = click.make_pass_decorator(NucypherClickConfig, ensure=True)


#
# Common CLI
#

@click.group()
@click.option('--version', help="Echo the CLI version", is_flag=True, callback=echo_version, expose_value=False, is_eager=True)
@click.option('-v', '--verbose', help="Specify verbosity level", count=True)
@uses_config
def nucypher_cli(config, verbose):
    click.echo(BANNER)
    config.verbose = verbose
    if config.verbose:
        click.secho("Verbose mode is enabled", fg='blue')


@nucypher_cli.command()
@uses_config
def status(config):
    """
    Echo a snapshot of live network metadata.
    """
    #
    # Initialize
    #
    ursula_config = UrsulaConfiguration.from_configuration_file()
    if not ursula_config.federated_only:
        ursula_config.connect_to_blockchain(config)
        ursula_config.connect_to_contracts(config)

        contract_payload = """

        | NuCypher ETH Contracts |

        Provider URI ............. {provider_uri}
        Registry Path ............ {registry_filepath}

        NucypherToken ............ {token}
        MinerEscrow .............. {escrow}
        PolicyManager ............ {manager}

        """.format(provider_uri=ursula_config.blockchain.interface.provider_uri,
                   registry_filepath=ursula_config.blockchain.interface.registry.filepath,
                   token=ursula_config.token_agent.contract_address,
                   escrow=ursula_config.miner_agent.contract_address,
                   manager=ursula_config.policy_agent.contract_address,
                   period=ursula_config.miner_agent.get_current_period())
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
    known_nodes = ursula_config.read_known_nodes()
    known_certificate_files = os.listdir(ursula_config.known_certificates_dir)
    number_of_known_nodes = len(known_nodes)
    seen_nodes = len(known_certificate_files)

    # Operating Mode
    federated_only = ursula_config.federated_only
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
        if node.checksum_public_address == ursula_config.checksum_address:
            node_type = 'self'
            row_template += ' ({})'.format(node_type)
        if node.checksum_public_address in seednode_addresses:
            node_type = 'seednode'
            row_template += ' ({})'.format(node_type)
        click.secho(row_template.format(node.checksum_public_address,
                                        node.rest_url(),
                                        node.timestamp), fg=color_index[node_type])


@nucypher_cli.command()
@click.argument('action')
@click.option('--debug', '-D', help="Enable debugging mode", is_flag=True)
@click.option('--dev', '-d', help="Enable development mode", is_flag=True)
@click.option('--force', '-f', help="Don't ask for confirmation", is_flag=True)
@click.option('--teacher-uri', help="An Ursula URI to start learning from (seednode)", type=click.STRING)
@click.option('--min-stake', help="The minimum stake the teacher must have to be a teacher", type=click.INT, default=0)
@click.option('--rest-host', help="The host IP address to run Ursula network services on", type=click.STRING)
@click.option('--rest-port', help="The host port to run Ursula network services on", type=click.IntRange(min=49151, max=65535, clamp=False))
@click.option('--db-filepath', help="The database filepath to connect to", type=click.STRING)
@click.option('--checksum-address', help="Run with a specified account", type=CHECKSUM_ADDRESS)
@click.option('--federated-only', help="Connect only to federated nodes", is_flag=True, default=True)
@click.option('--poa', help="Inject POA middleware", is_flag=True)
@click.option('--config-root', help="Custom configuration directory", type=click.Path())
@click.option('--config-file', help="Path to configuration file", type=click.Path(exists=True, dir_okay=False, file_okay=True, readable=True))
@click.option('--metadata-dir', help="Custom known metadata directory", type=click.Path(exists=True, dir_okay=True, file_okay=False, writable=True))
@click.option('--provider-uri', help="Blockchain provider's URI", type=click.STRING)
@click.option('--no-registry', help="Skip importing the default contract registry", is_flag=True)
@click.option('--registry-filepath', help="Custom contract registry filepath", type=click.Path(exists=True, dir_okay=False, file_okay=True, readable=True))
@uses_config
def ursula(config,
           action,
           debug,
           dev,
           force,
           teacher_uri,
           min_stake,
           rest_host,
           rest_port,
           db_filepath,
           checksum_address,
           federated_only,
           poa,
           config_root,
           config_file,
           metadata_dir,
           provider_uri,
           no_registry,
           registry_filepath
           ) -> None:
    """
    Manage and run an Ursula node.

    \b
    Actions
    -------------------------------------------------
    \b
    run            Run an "Ursula" node.
    init           Create a new Ursula node configuration.
    view           View the Ursula node's configuration.
    forget         Forget all known nodes.
    save-metadata  Manually write node metadata to disk without running
    destroy        Delete Ursula node configuration.

    """
    log = Logger('ursula.cli')

    #
    # Boring Setup Stuff
    #
    if debug:
        config.log_to_sentry = False
        config.log_to_file = True
        globalLogPublisher.removeObserver(logToSentry)                          # Sentry
        globalLogPublisher.addObserver(SimpleObserver(log_level_name='debug'))  # Print

    #
    # Launch Warnings
    #
    if dev:
        click.secho("WARNING: Running in development mode", fg='yellow')
    if federated_only:
        click.secho("WARNING: Running in Federated mode", fg='yellow')
    if force:
        click.secho("WARNING: Force is enabled", fg='yellow')

    #
    # Unauthenticated Configurations
    #
    if action == "init":
        """Create a brand-new persistent Ursula"""

        if dev:
            click.secho("WARNING: Using temporary storage area", fg='yellow')

        # Get password
        password = os.environ.get(KEYRING_PASSWORD_ENVVAR, NO_ENVVAR)
        if password is NO_ENVVAR:  # Collect password, prefer env var
            password = click.prompt("Enter keyring password", hide_input=True)

        ursula_config = UrsulaConfiguration.generate(password=password,
                                                     rest_host=rest_host,
                                                     rest_port=rest_port,
                                                     config_root=config_root,
                                                     db_filepath=db_filepath,
                                                     federated_only=federated_only,
                                                     checksum_address=checksum_address,
                                                     no_registry=federated_only or no_registry,
                                                     registry_filepath=registry_filepath,
                                                     provider_uri=provider_uri)

        click.secho("Generated keyring {}".format(ursula_config.keyring_dir), fg='green')
        click.secho("Saved configuration file {}".format(ursula_config.config_file_location), fg='green')

        # Give the use a suggestion as to what to do next...
        how_to_run_message = "\nTo run an Ursula node from the default configuration filepath run: \n\n'{}'\n"
        suggested_command = 'nucypher ursula run'
        if config_root is not None:
            config_file_location = os.path.join(config_root, config_file or UrsulaConfiguration.CONFIG_FILENAME)
            suggested_command += ' --config-file {}'.format(config_file_location)
        click.secho(how_to_run_message.format(suggested_command), fg='green')
        return  # FIN

    # Development Configuration
    if dev:
        ursula_config = UrsulaConfiguration(dev_mode=True,
                                            poa=poa,
                                            registry_filepath=registry_filepath,
                                            provider_uri=provider_uri,
                                            checksum_address=checksum_address,
                                            federated_only=federated_only,
                                            rest_host=rest_host,
                                            rest_port=rest_port,
                                            db_filepath=db_filepath)
    # Authenticated Configurations
    else:

        # Restore configuration from file
        ursula_config = UrsulaConfiguration.from_configuration_file(filepath=config_file
                                                                    # TODO: CLI Overrides
                                                                    # poa = poa,
                                                                    # registry_filepath = registry_filepath,
                                                                    # provider_uri = provider_uri,
                                                                    # checksum_address = checksum_address,
                                                                    # federated_only = federated_only,
                                                                    # rest_host = rest_host,
                                                                    # rest_port = rest_port,
                                                                    # db_filepath = db_filepath
                                                                    )

        # Get password
        password = os.environ.get(KEYRING_PASSWORD_ENVVAR, NO_ENVVAR)
        if password is NO_ENVVAR:  # Collect password, prefer env var
            password = click.prompt("Enter keyring password", hide_input=True)

        # Unlock keyring
        try:
            click.secho('Decrypting keyring...', fg='blue')
            ursula_config.keyring.unlock(password=password)  # Takes ~3 seconds, ~1GB Ram
        except CryptoError:
            raise ursula_config.keyring.AuthenticationFailed

    config.ursula_config = ursula_config  # Pass Ursula's config onto staking sub-command

    #
    # Action Switch
    #
    if action == 'run':
        """Seed, Produce, Run!"""

        #
        # Seed - Step 1
        #
        teacher_nodes = list()
        if teacher_uri:
            node = Teacher.from_teacher_uri(teacher_uri=teacher_uri,
                                            min_stake=min_stake,
                                            federated_only=federated_only)
            teacher_nodes.append(node)
        #
        # Produce - Step 2
        #
        ursula = ursula_config.produce()
        ursula_config.log.debug("Initialized Ursula {}".format(ursula), fg='green')

        # GO!
        try:

            #
            # Run - Step 3
            #
            click.secho("Running Ursula on {}".format(ursula.rest_interface), fg='green', bold=True)
            if not debug:
                stdio.StandardIO(UrsulaCommandProtocol(ursula=ursula))
            ursula.get_deployer().run()

        except Exception as e:
            ursula_config.log.critical(str(e))
            click.secho("{} {}".format(e.__class__.__name__, str(e)), fg='red')
            raise  # Crash :-(

        finally:
            click.secho("Stopping Ursula")
            ursula_config.cleanup()
            click.secho("Ursula Stopped", fg='red')
        return

    elif action == "save-metadata":
        """Manually save a node self-metadata file"""

        ursula = ursula_config.produce(ursula_config=ursula_config)
        metadata_path = ursula.write_node_metadata(node=ursula)
        click.secho("Successfully saved node metadata to {}.".format(metadata_path), fg='green')
        return

    elif action == "view":
        """Paint an existing configuration to the console"""

        paint_configuration(config_filepath=config_file or ursula_config.config_file_location)
        return

    elif action == "forget":
        """Forget all known nodes via storages"""

        click.confirm("Permanently delete all known node data?", abort=True)
        ursula_config.forget_nodes()
        message = "Removed all stored node node metadata and certificates"
        click.secho(message=message, fg='red')
        return

    elif action == "destroy":
        """Delete all configuration files from the disk"""

        if not force:
            click.confirm('''
*Permanently and irreversibly delete all* nucypher files including:
    - Private and Public Keys
    - Known Nodes
    - TLS certificates
    - Node Configurations
    - Log Files

Delete {}?'''.format(ursula_config.config_root), abort=True)

        try:
            ursula_config.destroy(force=force)
        except FileNotFoundError:
            message = 'Failed: No nucypher files found at {}'.format(ursula_config.config_root)
            click.secho(message, fg='red')
            log.debug(message)
            raise click.Abort()
        else:
            message = "Deleted configuration files at {}".format(ursula_config.config_root)
            click.secho(message, fg='green')
            log.debug(message)
        return

    else:
        raise click.BadArgumentUsage("No such argument {}".format(action))


@click.argument('action', default='list', required=False)
@click.option('--checksum-address', type=CHECKSUM_ADDRESS)
@click.option('--value', help="Token value of stake", type=click.IntRange(min=MIN_ALLOWED_LOCKED, max=MIN_ALLOWED_LOCKED, clamp=False))
@click.option('--duration', help="Period duration of stake", type=click.IntRange(min=MIN_LOCKED_PERIODS, max=MAX_MINTING_PERIODS, clamp=False))
@click.option('--index', help="A specific stake index to resume", type=click.INT)
@uses_config
def stake(config,
          action,
          checksum_address,
          index,
          value,
          duration):
    """
    Manage token staking.

    \b
    Actions
    -------------------------------------------------
    \b
    list              List all stakes for this node.
    init              Stage a new stake.
    confirm-activity  Manually confirm-activity for the current period.
    divide            Divide an existing stake.
    collect-reward    Withdraw staking reward.

    """

    #
    # Initialize
    #
    if not config.federated_only:
        config.ursula_config.connect_to_blockchain(config)
        config.ursula_config.connect_to_contracts(config)

    if not checksum_address:

        if config.accounts == NO_BLOCKCHAIN_CONNECTION:
            click.echo('No account found.')
            raise click.Abort()

        for index, address in enumerate(config.accounts):
            if index == 0:
                row = 'etherbase (0) | {}'.format(address)
            else:
                row = '{} .......... | {}'.format(index, address)
            click.echo(row)

        click.echo("Select ethereum address")
        account_selection = click.prompt("Enter 0-{}".format(len(config.accounts)), type=click.INT)
        address = config.ursula_config.accounts[account_selection]

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
        # TODO: Implement
        # click.confirm("Send {} to {}?".format)
        # config.miner_agent.collect_staking_reward(collector_address=address)
        raise NotImplementedError

    else:
        raise click.BadArgumentUsage("No such argument {}".format(action))
