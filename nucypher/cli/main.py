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
from eth_utils import is_checksum_address
from sentry_sdk.integrations.logging import LoggingIntegration
from twisted.internet import stdio
from twisted.logger import Logger
from twisted.logger import globalLogPublisher

import nucypher
from constant_sorrow.constants import NO_NODE_CONFIGURATION, NO_BLOCKCHAIN_CONNECTION
from nucypher.blockchain.eth.constants import (MIN_ALLOWED_LOCKED,
                                               MIN_LOCKED_PERIODS,
                                               MAX_MINTING_PERIODS)
from nucypher.cli.constants import NUCYPHER_SENTRY_ENDPOINT, BANNER
from nucypher.cli.protocol import UrsulaCommandProtocol
from nucypher.cli.utilities import (
    connect_to_contracts,
    connect_to_blockchain,
    create_account,
    destroy_configuration,
    forget_nodes,
    attempt_seednode_learning,
    echo_version,
    CHECKSUM_ADDRESS,
    write_configuration,
    unlock_and_produce,
    paint_configuration, get_ursula_configuration)
from nucypher.config.constants import SEEDNODES
from nucypher.config.keyring import NucypherKeyring
from nucypher.utilities.logging import logToSentry, getTextFileObserver, simpleObserver


class NucypherClickConfig:

    # Set to False to completely opt-out of sentry reporting
    log_to_sentry = True   # TODO: Use envvar
    log_to_file = True     # TODO: Use envvar

    def __init__(self):

        #
        # Logging
        #

        # Sentry
        if self.log_to_sentry:
            import sentry_sdk
            import logging

            sentry_logging = LoggingIntegration(
                level=logging.INFO,        # Capture info and above as breadcrumbs
                event_level=logging.DEBUG  # Send debug logs as events
            )
            sentry_sdk.init(
                dsn=NUCYPHER_SENTRY_ENDPOINT,
                integrations=[sentry_logging],
                release=nucypher.__version__
            )

            globalLogPublisher.addObserver(logToSentry)

        # Files
        if self.log_to_file is True:
            globalLogPublisher.addObserver(getTextFileObserver())

        # Emission
        self.log = Logger(self.__class__.__name__)


#
# Register the above class as a decorator
#
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
    ursula_config = get_ursula_configuration()
    if not ursula_config.federated_only:
        connect_to_blockchain(config)
        connect_to_contracts(config)

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
    ursula_config = get_ursula_configuration(checksum_address=checksum_address)
    if not ursula_config.federated_only:
        connect_to_blockchain(config)
        connect_to_contracts(config)

        if not checksum_address:
            checksum_address = ursula_config.blockchain.interface.w3.eth.coinbase
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
        new_address = create_account(config)
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

        passphrase = click.prompt("Enter passphrase to decrypt account",
                                  type=click.STRING,
                                  hide_input=True,
                                  confirmation_prompt=True)

        keyring._export_wallet_to_node(blockchain=config.blockchain, passphrase=passphrase)

    elif action == 'list':
        if config.accounts == NO_BLOCKCHAIN_CONNECTION:
            click.echo('No account found.')
            raise click.Abort()

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


#
# Ursula CLI
#

@nucypher_cli.command()
@click.argument('action')
@click.option('--debug', '-D', help="Enable debugging mode", is_flag=True)
@click.option('--dev', '-d', help="Enable development mode", is_flag=True)
@click.option('--force', '-f', help="Don't ask for confirmation", is_flag=True)
@click.option('--teacher-uri', help="An Ursula URI to start learning from (seednode)", type=click.STRING)
@click.option('--min-stake', help="The minimum stake the teacher must have to be a teacher", type=click.INT, default=0)
@click.option('--rest-host', help="The host IP address to run Ursula network services on", type=click.STRING)
@click.option('--rest-port', help="The host port to run Ursula network services on", type=click.IntRange(min=49151, max=65535, clamp=False))
@click.option('--db-name', help="The database name to connect to", type=click.STRING)
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
           db_name,
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
    destroy        Delete Ursula node configuration.

    """

    #
    # Boring Setup Stuff
    #

    # Launch Logger
    log = Logger('ursula.launch')

    if force:
        click.secho("WARNING: Force is enabled", fg='yellow')

    if debug:
        globalLogPublisher.removeObserver(logToSentry)  # Sentry
        config.log_to_sentry = False
        globalLogPublisher.addObserver(simpleObserver)  # Print

    #
    # Configure - Step 0
    #
    ursula_config = get_ursula_configuration(dev_mode=dev,
                                             poa=poa,
                                             config_file=config_file,
                                             metadata_dir=metadata_dir,
                                             provider_uri=provider_uri,
                                             checksum_address=checksum_address,
                                             federated_only=federated_only,
                                             rest_host=rest_host,
                                             rest_port=rest_port,
                                             db_name=db_name)

    config.ursula = ursula  # Pass Ursula onto staking sub-command

    #
    # Launch Warnings
    #
    if ursula_config.dev:
        click.secho("WARNING: Running in development mode", fg='yellow')
    else:
        click.secho("WARNING: Development mode is disabled", fg='yellow')

    if ursula_config.federated_only:
        click.secho("WARNING: Running in Federated mode", fg='yellow')

    if action == "init":
        write_configuration(ursula_config=ursula_config,
                            no_registry=federated_only or no_registry,
                            rest_host=rest_host)

    elif action == 'run':
        #
        # Seed - Step 1
        #
        teacher_nodes = list()
        if teacher_uri:
            node = attempt_seednode_learning(ursula_config, teacher_uri, min_stake)
            teacher_nodes.append(node)
        #
        # Produce - Step 2
        #
        URSULA = unlock_and_produce(ursula_config=ursula_config, teacher_nodes=teacher_nodes)
        log.debug("Initialized Ursula {}".format(URSULA), fg='green')

        # GO!
        try:

            #
            # Run - Step 3
            #
            click.secho("Running Ursula on {}".format(URSULA.rest_interface), fg='green', bold=True)
            if not debug:
                stdio.StandardIO(UrsulaCommandProtocol(ursula=URSULA))
            URSULA.get_deployer().run()

        except Exception as e:
            config.log.critical(str(e))
            click.secho("{} {}".format(e.__class__.__name__, str(e)), fg='red')
            raise  # Crash :-(

        finally:
            click.secho("Stopping Ursula")
            ursula_config.cleanup()
            click.secho("Ursula Stopped", fg='red')

    #
    # Utilities; Not Steps
    #
    elif action == "save-metadata":
        URSULA = unlock_and_produce(ursula_config=ursula_config)
        metadata_path = URSULA.write_node_metadata(node=URSULA)
        click.secho("Successfully saved node metadata to {}.".format(metadata_path), fg='green')

    elif action == "destroy":
        destroy_configuration(ursula_config=ursula_config, force=force)

    elif action == "view":
        paint_configuration(ursula_config=ursula_config)

    elif action == "forget":
        forget_nodes(config)

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
    ursula = get_ursula_configuration()
    if not config.federated_only:
        connect_to_blockchain(config)
        connect_to_contracts(config)

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
        # address = config.accounts[account_selection]

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
        raise click.BadArgumentUsage
