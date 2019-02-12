"""
This file is part of nucypher.

nucypher is free software: you can redistribute it and/or modify
it under the terms of the GNU Affero General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

nucypher is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU Affero General Public License for more details.

You should have received a copy of the GNU Affero General Public License
along with nucypher.  If not, see <https://www.gnu.org/licenses/>.

"""

import os

import click
from constant_sorrow.constants import TEMPORARY_DOMAIN
from twisted.internet import stdio
from twisted.logger import Logger
from twisted.logger import globalLogPublisher

from nucypher.blockchain.eth.actors import Miner
from nucypher.blockchain.eth.constants import MIN_LOCKED_PERIODS, MAX_MINTING_PERIODS
from nucypher.characters.banners import URSULA_BANNER
from nucypher.cli import actions
from nucypher.cli.actions import destroy_system_configuration
from nucypher.cli.config import nucypher_click_config
from nucypher.cli.processes import UrsulaCommandProtocol
from nucypher.cli.types import (
    EIP55_CHECKSUM_ADDRESS,
    NETWORK_PORT,
    EXISTING_READABLE_FILE,
    EXISTING_WRITABLE_DIRECTORY
)
from nucypher.config.characters import UrsulaConfiguration
from nucypher.utilities.logging import (
    logToSentry,
    getJsonFileObserver,
    SimpleObserver, GlobalConsoleLogger)


@click.command()
@click.argument('action')
@click.option('--dev', '-d', help="Enable development mode", is_flag=True)
@click.option('--quiet', '-Q', help="Disable logging", is_flag=True)
@click.option('--dry-run', '-x', help="Execute normally without actually starting the node", is_flag=True)
@click.option('--force', help="Don't ask for confirmation", is_flag=True)
@click.option('--lonely', help="Do not connect to seednodes", is_flag=True)
@click.option('--network', help="Network Domain Name", type=click.STRING)
@click.option('--teacher-uri', help="An Ursula URI to start learning from (seednode)", type=click.STRING)
@click.option('--min-stake', help="The minimum stake the teacher must have to be a teacher", type=click.INT, default=0)
@click.option('--rest-host', help="The host IP address to run Ursula network services on", type=click.STRING)
@click.option('--rest-port', help="The host port to run Ursula network services on", type=NETWORK_PORT)
@click.option('--db-filepath', help="The database filepath to connect to", type=click.STRING)
@click.option('--checksum-address', help="Run with a specified account", type=EIP55_CHECKSUM_ADDRESS)
@click.option('--federated-only', '-F', help="Connect only to federated nodes", is_flag=True)
@click.option('--poa', help="Inject POA middleware", is_flag=True)
@click.option('--config-root', help="Custom configuration directory", type=click.Path())
@click.option('--config-file', help="Path to configuration file", type=EXISTING_READABLE_FILE)
@click.option('--metadata-dir', help="Custom known metadata directory", type=EXISTING_WRITABLE_DIRECTORY)
@click.option('--provider-uri', help="Blockchain provider's URI", type=click.STRING)
@click.option('--recompile-solidity', help="Compile solidity from source when making a web3 connection", is_flag=True)
@click.option('--no-registry', help="Skip importing the default contract registry", is_flag=True)
@click.option('--registry-filepath', help="Custom contract registry filepath", type=EXISTING_READABLE_FILE)
@click.option('--checksum-address', type=EIP55_CHECKSUM_ADDRESS)
@click.option('--value', help="Token value of stake", type=click.INT)
@click.option('--duration', help="Period duration of stake", type=click.INT)
@click.option('--index', help="A specific stake index to resume", type=click.INT)
@click.option('--list', '-l', 'list_', help="List all blockchain stakes", is_flag=True)
@nucypher_click_config
def ursula(click_config,
           action,
           dev,
           quiet,
           dry_run,
           force,
           lonely,
           network,
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
           metadata_dir,  # TODO: Start nodes from an additional existing metadata dir
           provider_uri,
           recompile_solidity,
           no_registry,
           registry_filepath,
           value,
           duration,
           index,
           list_
           ) -> None:
    """
    Manage and run an "Ursula" PRE node.

    \b
    Actions
    -------------------------------------------------
    \b
    init              Create a new Ursula node configuration.
    view              View the Ursula node's configuration.
    run               Run an "Ursula" node.
    save-metadata     Manually write node metadata to disk without running
    forget            Forget all known nodes.
    destroy           Delete Ursula node configuration.
    stake             Manage stakes for this node.
    confirm-activity  Manually confirm-activity for the current period.
    divide-stake      Divide an existing stake.
    collect-reward    Withdraw staking reward.

    """

    #
    # Boring Setup Stuff
    #
    if not quiet:
        log = Logger('ursula.cli')

    if click_config.debug and quiet:
        raise click.BadOptionUsage(option_name="quiet", message="--debug and --quiet cannot be used at the same time.")

    if click_config.debug:
        click_config.log_to_sentry = False
        click_config.log_to_file = True
        globalLogPublisher.removeObserver(logToSentry)  # Sentry
        GlobalConsoleLogger.set_log_level(log_level_name='debug')

    elif quiet:
        globalLogPublisher.removeObserver(logToSentry)
        globalLogPublisher.removeObserver(SimpleObserver)
        globalLogPublisher.removeObserver(getJsonFileObserver())

    if not click_config.json_ipc and not click_config.quiet:
        click.secho(URSULA_BANNER)

    #
    # Pre-Launch Warnings
    #
    if not quiet:
        if dev:
            click.secho("WARNING: Running in development mode", fg='yellow')
        if force:
            click.secho("WARNING: Force is enabled", fg='yellow')

    #
    # Unauthenticated Configurations & Unconfigured Ursula Control
    #
    if action == "init":
        """Create a brand-new persistent Ursula"""

        if not network:
            raise click.BadArgumentUsage('--network is required to initialize a new configuration.')

        if dev:
            actions.handle_control_output(message="WARNING: Using temporary storage area",
                                          color='yellow',
                                          quiet=quiet,
                                          json=click_config.json)

        if not config_root:  # Flag
            config_root = click_config.config_file  # Envvar

        if not rest_host:
            rest_host = click.prompt("Enter Ursula's public-facing IPv4 address")  # TODO: Remove this step

        ursula_config = UrsulaConfiguration.generate(password=click_config._get_password(confirm=True),
                                                     config_root=config_root,
                                                     rest_host=rest_host,
                                                     rest_port=rest_port,
                                                     db_filepath=db_filepath,
                                                     domains={network} if network else None,
                                                     federated_only=federated_only,
                                                     checksum_public_address=checksum_address,
                                                     no_registry=federated_only or no_registry,
                                                     registry_filepath=registry_filepath,
                                                     provider_uri=provider_uri,
                                                     poa=poa)

        click_config.emitter(message="Generated keyring {}".format(ursula_config.keyring_dir), color='green')

        click_config.emitter(message="Saved configuration file {}".format(ursula_config.config_file_location), color='green')

        # Give the use a suggestion as to what to do next...
        how_to_run_message = "\nTo run an Ursula node from the default configuration filepath run: \n\n'{}'\n"
        suggested_command = 'nucypher ursula run'
        if config_root is not None:
            config_file_location = os.path.join(config_root, config_file or UrsulaConfiguration.CONFIG_FILENAME)
            suggested_command += ' --config-file {}'.format(config_file_location)

        return click_config.emitter(message=how_to_run_message.format(suggested_command), color='green')

    #
    # Configured Ursulas
    #

    # Development Configuration
    if dev:
        ursula_config = UrsulaConfiguration(dev_mode=True,
                                            domains={TEMPORARY_DOMAIN},
                                            poa=poa,
                                            registry_filepath=registry_filepath,
                                            provider_uri=provider_uri,
                                            checksum_public_address=checksum_address,
                                            federated_only=federated_only,
                                            rest_host=rest_host,
                                            rest_port=rest_port,
                                            db_filepath=db_filepath)
    # Authenticated Configurations
    else:

        ursula_config = UrsulaConfiguration.from_configuration_file(filepath=config_file,
                                                                    domains=[str(network)] if network else None,
                                                                    registry_filepath=registry_filepath,
                                                                    provider_uri=provider_uri,
                                                                    rest_host=rest_host,
                                                                    rest_port=rest_port,
                                                                    db_filepath=db_filepath,
                                                                    poa=poa)

        click_config.unlock_keyring(node_configuration=ursula_config, quiet=quiet)

    #
    # Connect to Blockchain
    #
    if not ursula_config.federated_only:
        actions.connect_to_blockchain(configuration=ursula_config, recompile_contracts=recompile_solidity)

    click_config.ursula_config = ursula_config  # Pass Ursula's config onto staking sub-command

    #
    # Launch Warnings
    #

    if ursula_config.federated_only:
        click_config.emitter(message="WARNING: Running in Federated mode", color='yellow'
                             )
    #
    # Action Switch
    #
    if action == 'run':
        """Seed, Produce, Run!"""

        #
        # Seed - Step 1
        #
        teacher_uris = [teacher_uri] if teacher_uri else list()
        teacher_nodes = actions.load_seednodes(teacher_uris=teacher_uris,
                                               min_stake=min_stake,
                                               federated_only=federated_only,
                                               network_middleware=click_config.middleware)


        #
        # Produce - Step 2
        #
        URSULA = ursula_config(known_nodes=teacher_nodes, lonely=lonely)

        # GO!
        try:

            #
            # Run - Step 3
            #
            click_config.emitter(
                message="Connecting to {}".format(','.join(str(d) for d in ursula_config.domains)),
                color='green',
                bold=True)

            click_config.emitter(
                message="Running Ursula {} on {}".format(URSULA, URSULA.rest_interface),
                color='green',
                bold=True)
            
            if not click_config.debug:
                stdio.StandardIO(UrsulaCommandProtocol(ursula=URSULA))

            if dry_run:
                # That's all folks!
                return

            URSULA.get_deployer().run()  # <--- Blocking Call (Reactor)

        except Exception as e:
            ursula_config.log.critical(str(e))
            click_config.emitter(
                message="{} {}".format(e.__class__.__name__, str(e)),
                color='red',
                bold=True)
            raise  # Crash :-(

        finally:
            click_config.emitter(message="Stopping Ursula", color='green')
            ursula_config.cleanup()
            click_config.emitter(message="Ursula Stopped", color='red')
        return

    elif action == "save-metadata":
        """Manually save a node self-metadata file"""

        URSULA = ursula_config.produce(ursula_config=ursula_config)
        metadata_path = ursula.write_node_metadata(node=URSULA)
        return click_config.emitter(message="Successfully saved node metadata to {}.".format(metadata_path), color='green')

    elif action == "view":
        """Paint an existing configuration to the console"""
        response = UrsulaConfiguration._read_configuration_file(filepath=config_file or ursula_config.config_file_location)
        return click_config.emitter(response=response)

    elif action == "forget":
        # TODO: Move to character control
        actions.forget(configuration=ursula_config)
        return

    elif action == "destroy":
        """Delete all configuration files from the disk"""

        if dev:
            message = "'nucypher ursula destroy' cannot be used in --dev mode"
            raise click.BadOptionUsage(option_name='--dev', message=message)

        destroyed_filepath = destroy_system_configuration(config_class=UrsulaConfiguration,
                                                          config_file=config_file,
                                                          network=network,
                                                          config_root=ursula_config.config_file_location,
                                                          force=force)

        return click_config.emitter(message=f"Destroyed {destroyed_filepath}", color='green')

    elif action == 'stake':

        if list_:
            live_stakes = list(ursula_config.miner_agent.get_all_stakes(miner_address=checksum_address))
            if not live_stakes:
                click.echo(f"There are no existing stakes for {ursula_config.checksum_public_address}")

            for index, stake_info in enumerate(live_stakes):
                row = '{} | {}'.format(index, stake_info)
                click.echo(row)
            return

        if not force:
            click.confirm("Stage a new stake?", abort=True)
            if not quiet:
                click.secho("Staging new stake")

        live_stakes = list(ursula_config.miner_agent.get_all_stakes(miner_address=checksum_address))
        if len(live_stakes) > 0:
            raise RuntimeError("There is an existing stake for {}".format(checksum_address))

        # Value
        balance = ursula_config.token_agent.get_balance(address=checksum_address)

        if not quiet:
            click.echo("Current balance: {}".format(balance))

        if not value:
            value = click.prompt("Enter stake value", type=click.INT)

        # Duration
        if not quiet:
            message = "Minimum duration: {} | Maximum Duration: {}".format(MIN_LOCKED_PERIODS, MAX_MINTING_PERIODS)
            click.echo(message)

        if not duration:
            duration = click.prompt("Enter stake duration in periods (1 Period = 24 Hours)", type=click.INT)

        start_period = ursula_config.miner_agent.get_current_period()
        end_period = start_period + duration

        if not force:  # Review
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

        miner = Miner(is_me=True,
                      checksum_address=ursula_config.checksum_public_address,
                      blockchain=ursula_config.blockchain)

        result = miner.initialize_stake(amount=value, lock_periods=duration)
        for tx_name, txhash in result.items():
            click.secho(f'{tx_name} .......... {txhash}')
        else:
            click.secho('Successfully transmitted stake initialization transactions', fg='green')
        return

    elif action == 'confirm-activity':
        """Manually confirm activity for the active period"""
        stakes = ursula_config.miner_agent.get_all_stakes(miner_address=checksum_address)
        if len(stakes) == 0:
            raise RuntimeError("There are no active stakes for {}".format(checksum_address))
        ursula_config.miner_agent.confirm_activity(node_address=checksum_address)
        return

    elif action == 'divide-stake':
        """Divide an existing stake by specifying the new target value and end period"""

        stakes = list(ursula_config.miner_agent.get_all_stakes(miner_address=checksum_address))
        if len(stakes) == 0:
            raise RuntimeError("There are no active stakes for {}".format(checksum_address))

        if index is None:
            for selection_index, stake_info in enumerate(stakes):
                click.echo("{} ....... {}".format(selection_index, stake_info))
            index = click.prompt("Select a stake to divide", type=click.INT)

        if not value:
            target_value = click.prompt("Enter new target value", type=click.INT)
        else:
            target_value = value

        if not duration:
            extension = click.prompt("Enter number of periods to extend", type=click.INT)
        else:
            extension = duration

        if not force:
            click.echo("""
            Current Stake: {}

            New target value {}
            New end period: {}

            """.format(stakes[index],
                       target_value,
                       target_value + extension))

            click.confirm("Is this correct?", abort=True)

        miner = Miner(is_me=True,
                      checksum_address=ursula_config.checksum_public_address,
                      blockchain=ursula_config.blockchain)

        txhash_bytes = miner.divide_stake(stake_index=index,
                                          target_value=value,
                                          additional_periods=duration)

        if not quiet:
            click.secho('Successfully divided stake', fg='green')
            click.secho(f'Transaction Hash ........... {txhash_bytes.hex()}')

        return

    elif action == 'collect-reward':
        """Withdraw staking reward to the specified wallet address"""
        miner = Miner(checksum_address=checksum_address, blockchain=ursula_config.blockchain, is_me=True)

        if not force:
            click.confirm(f"Send {miner.calculate_reward()} to {ursula_config.checksum_public_address}?")

        miner.collect_staking_reward()

    else:
        raise click.BadArgumentUsage("No such argument {}".format(action))
