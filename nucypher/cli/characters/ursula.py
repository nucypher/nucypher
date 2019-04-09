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

import click
from constant_sorrow.constants import TEMPORARY_DOMAIN
from twisted.internet import stdio
from twisted.logger import Logger

from nucypher.blockchain.eth.constants import MIN_LOCKED_PERIODS, MAX_MINTING_PERIODS, MIN_ALLOWED_LOCKED
from nucypher.blockchain.eth.token import NU
from nucypher.characters.banners import URSULA_BANNER
from nucypher.cli import actions, painting
from nucypher.cli.config import nucypher_click_config
from nucypher.cli.processes import UrsulaCommandProtocol
from nucypher.cli.types import (
    EIP55_CHECKSUM_ADDRESS,
    NETWORK_PORT,
    EXISTING_READABLE_FILE,
    STAKE_DURATION,
    STAKE_EXTENSION,
    STAKE_VALUE
)
from nucypher.config.characters import UrsulaConfiguration
from nucypher.utilities.sandbox.constants import (
    TEMPORARY_DOMAIN,
)


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
@click.option('--withdraw-address', help="Send reward collection to an alternate address", type=EIP55_CHECKSUM_ADDRESS)
@click.option('--federated-only', '-F', help="Connect only to federated nodes", is_flag=True, default=None)
@click.option('--poa', help="Inject POA middleware", is_flag=True, default=None)
@click.option('--config-root', help="Custom configuration directory", type=click.Path())
@click.option('--config-file', help="Path to configuration file", type=EXISTING_READABLE_FILE)
@click.option('--provider-uri', help="Blockchain provider's URI", type=click.STRING)
@click.option('--recompile-solidity', help="Compile solidity from source when making a web3 connection", is_flag=True)
@click.option('--no-registry', help="Skip importing the default contract registry", is_flag=True)
@click.option('--registry-filepath', help="Custom contract registry filepath", type=EXISTING_READABLE_FILE)
@click.option('--value', help="Token value of stake", type=click.INT)
@click.option('--duration', help="Period duration of stake", type=click.INT)
@click.option('--index', help="A specific stake index to resume", type=click.INT)
@click.option('--list', '-l', 'list_', help="List all blockchain stakes", is_flag=True)
@click.option('--divide', '-d', help="Divide an existing stake into sub-stakes.", is_flag=True)
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
           withdraw_address,
           federated_only,
           poa,
           config_root,
           config_file,
           provider_uri,
           recompile_solidity,
           no_registry,
           registry_filepath,
           value,
           duration,
           index,
           list_,
           divide
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
    collect-reward    Withdraw staking reward.

    """

    #
    # Boring Setup Stuff
    #
    if not quiet:
        log = Logger('ursula.cli')

    if click_config.debug and quiet:
        raise click.BadOptionUsage(option_name="quiet", message="--debug and --quiet cannot be used at the same time.")

    if not click_config.json_ipc and not click_config.quiet:
        click.secho(URSULA_BANNER.format(checksum_address or ''))

    #
    # Pre-Launch Warnings
    #
    if not click_config.quiet:
        if dev:
            click.secho("WARNING: Running in Development mode", fg='yellow')
        if force:
            click.secho("WARNING: Force is enabled", fg='yellow')

    #
    # Unauthenticated Configurations & Un-configured Ursula Control
    #
    if action == "init":
        """Create a brand-new persistent Ursula"""

        if not network:
            raise click.BadArgumentUsage('--network is required to initialize a new configuration.')

        if dev:
            click_config.emit(message="WARNING: Using temporary storage area", color='yellow')

        if not config_root:                         # Flag
            config_root = click_config.config_file  # Envvar

        if not rest_host:
            rest_host = click.prompt("Enter Ursula's public-facing IPv4 address")  # TODO: Remove this step

        ursula_config = UrsulaConfiguration.generate(password=click_config.get_password(confirm=True),
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

        painting.paint_new_installation_help(new_configuration=ursula_config,
                                             config_root=config_root,
                                             config_file=config_file,
                                             federated_only=federated_only)
        return

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

        # Domains -> bytes | or default
        domains = set(bytes(network, encoding='utf-8')) if network else None

        # Load Ursula from Configuration File
        try:
            ursula_config = UrsulaConfiguration.from_configuration_file(filepath=config_file,
                                                                        domains=domains,
                                                                        registry_filepath=registry_filepath,
                                                                        provider_uri=provider_uri,
                                                                        rest_host=rest_host,
                                                                        rest_port=rest_port,
                                                                        db_filepath=db_filepath,
                                                                        poa=poa,
                                                                        federated_only=federated_only)
        except FileNotFoundError:
            return actions.handle_missing_configuration_file(character_config_class=UrsulaConfiguration,
                                                             config_file=config_file)

        click_config.unlock_keyring(character_configuration=ursula_config)

    # Handle destruction *before* network bootstrap and character initialization below
    if action == "destroy":
        """Delete all configuration files from the disk"""
        if dev:
            message = "'nucypher ursula destroy' cannot be used in --dev mode"
            raise click.BadOptionUsage(option_name='--dev', message=message)
        return actions.destroy_configuration(character_config=ursula_config, force=force)

    #
    # Connect to Blockchain (Non-Federated)
    #

    if not ursula_config.federated_only:
        click_config.connect_to_blockchain(character_configuration=ursula_config,
                                           recompile_contracts=recompile_solidity)

    click_config.ursula_config = ursula_config  # Pass Ursula's config onto staking sub-command

    #
    # Launch Warnings
    #

    if ursula_config.federated_only:
        click_config.emit(message="WARNING: Running in Federated mode", color='yellow')

    # Seed - Step 1
    teacher_uris = [teacher_uri] if teacher_uri else list()
    teacher_nodes = actions.load_seednodes(teacher_uris=teacher_uris,
                                           min_stake=min_stake,
                                           federated_only=ursula_config.federated_only,
                                           network_middleware=click_config.middleware)

    # Produce - Step 2
    URSULA = ursula_config(known_nodes=teacher_nodes, lonely=lonely)

    #
    # Action Switch
    #

    if action == 'run':
        """Seed, Produce, Run!"""

        # GO!
        try:

            click_config.emit(
                message="Starting Ursula on {}".format(URSULA.rest_interface),
                color='green',
                bold=True)

            # Ursula Deploy Warnings
            click_config.emit(
                message="Connecting to {}".format(','.join(str(d, encoding='utf-8') for d in ursula_config.domains)),
                color='green',
                bold=True)

            if not URSULA.federated_only and URSULA.stakes:
                click_config.emit(
                    message=f"Staking {str(URSULA.total_staked)} ~ Keep Ursula Online!",
                    color='blue',
                    bold=True)

            if not click_config.debug:
                stdio.StandardIO(UrsulaCommandProtocol(ursula=URSULA))

            if dry_run:
                return  # <-- ABORT -X (Last Chance)

            # Run - Step 3
            node_deployer = URSULA.get_deployer()
            node_deployer.addServices()
            node_deployer.catalogServers(node_deployer.hendrix)
            node_deployer.run()   # <--- Blocking Call (Reactor)

        # Handle Crash
        except Exception as e:
            ursula_config.log.critical(str(e))
            click_config.emit(
                message="{} {}".format(e.__class__.__name__, str(e)),
                color='red',
                bold=True)
            raise  # Crash :-(

        # Graceful Exit / Crash
        finally:
            click_config.emit(message="Stopping Ursula", color='green')
            ursula_config.cleanup()
            click_config.emit(message="Ursula Stopped", color='red')
        return

    elif action == "save-metadata":
        """Manually save a node self-metadata file"""
        metadata_path = ursula.write_node_metadata(node=URSULA)
        return click_config.emit(message="Successfully saved node metadata to {}.".format(metadata_path), color='green')

    elif action == "view":
        """Paint an existing configuration to the console"""
        response = UrsulaConfiguration._read_configuration_file(filepath=config_file or ursula_config.config_file_location)
        return click_config.emit(response=response)

    elif action == "forget":
        actions.forget(configuration=ursula_config)
        return

    elif action == 'stake':

        # List Only
        if list_:
            if not URSULA.stakes:
                click.echo(f"There are no existing stakes for {URSULA.checksum_public_address}")
            painting.paint_stakes(stakes=URSULA.stakes)
            return

        # Divide Only
        if divide:
            """Divide an existing stake by specifying the new target value and end period"""

            # Validate
            if len(URSULA.stakes) == 0:
                click.secho("There are no active stakes for {}".format(URSULA.checksum_public_address))
                return

            # Selection
            if index is None:
                painting.paint_stakes(stakes=URSULA.stakes)
                index = click.prompt("Select a stake to divide", type=click.IntRange(min=0, max=len(URSULA.stakes)-1))

            # Lookup the stake
            current_stake = URSULA.stakes[index]

            # Value
            if not value:
                value = click.prompt(f"Enter target value (must be less than {str(current_stake.value)})", type=STAKE_VALUE)
            value = NU(value, 'NU')

            # Duration
            if not duration:
                extension = click.prompt("Enter number of periods to extend", type=STAKE_EXTENSION)
            else:
                extension = duration

            if not force:
                painting.paint_staged_stake_division(ursula=URSULA,
                                                     original_index=index,
                                                     original_stake=current_stake,
                                                     target_value=value,
                                                     extension=extension)

                click.confirm("Is this correct?", abort=True)

            txhash_bytes = URSULA.divide_stake(stake_index=index,
                                               target_value=value,
                                               additional_periods=extension)

            if not quiet:
                click.secho('Successfully divided stake', fg='green')
                click.secho(f'Transaction Hash ........... {txhash_bytes.hex()}')

            # Show the resulting stake list
            painting.paint_stakes(stakes=URSULA.stakes)

            return

        # Confirm new stake init
        if not force:
            click.confirm("Stage a new stake?", abort=True)

        # Validate balance
        balance = URSULA.token_balance
        if balance == 0:
            click.secho(f"{ursula.checksum_public_address} has 0 NU.")
            raise click.Abort
        if not quiet:
            click.echo(f"Current balance: {balance}")

        # Gather stake value
        if not value:
            value = click.prompt(f"Enter stake value", type=STAKE_VALUE, default=NU(MIN_ALLOWED_LOCKED, 'NuNit'))
        else:
            value = NU(int(value), 'NU')

        # Duration
        if not quiet:
            message = "Minimum duration: {} | Maximum Duration: {}".format(MIN_LOCKED_PERIODS, MAX_MINTING_PERIODS)
            click.echo(message)
        if not duration:
            duration = click.prompt("Enter stake duration in periods (1 Period = 24 Hours)", type=STAKE_DURATION)
        start_period = URSULA.miner_agent.get_current_period()
        end_period = start_period + duration

        # Review
        if not force:
            painting.paint_staged_stake(ursula=URSULA,
                                        stake_value=value,
                                        duration=duration,
                                        start_period=start_period,
                                        end_period=end_period)

            if not dev:
                actions.confirm_staged_stake(ursula=URSULA, value=value, duration=duration)

        # Last chance to bail
        if not force:
            click.confirm("Publish staged stake to the blockchain?", abort=True)

        staking_transactions = URSULA.initialize_stake(amount=int(value), lock_periods=duration)
        painting.paint_staking_confirmation(ursula=URSULA, transactions=staking_transactions)
        return

    elif action == 'confirm-activity':
        if not URSULA.stakes:
            click.secho("There are no active stakes for {}".format(URSULA.checksum_public_address))
            return
        URSULA.miner_agent.confirm_activity(node_address=URSULA.checksum_public_address)
        return

    elif action == 'collect-reward':
        """Withdraw staking reward to the specified wallet address"""
        if not force:
            click.confirm(f"Send {URSULA.calculate_reward()} to {URSULA.checksum_public_address}?")

        URSULA.collect_policy_reward(collector_address=withdraw_address or checksum_address)
        URSULA.collect_staking_reward()

    else:
        raise click.BadArgumentUsage("No such argument {}".format(action))
