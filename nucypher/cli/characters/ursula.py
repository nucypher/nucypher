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
from constant_sorrow.constants import NO_BLOCKCHAIN_CONNECTION
from twisted.internet import stdio

from nucypher.characters.banners import URSULA_BANNER
from nucypher.cli import actions, painting
from nucypher.cli.actions import get_password
from nucypher.cli.config import nucypher_click_config
from nucypher.cli.processes import UrsulaCommandProtocol
from nucypher.cli.types import (
    EIP55_CHECKSUM_ADDRESS,
    NETWORK_PORT,
    EXISTING_READABLE_FILE)
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
@click.option('--federated-only', '-F', help="Connect only to federated nodes", is_flag=True, default=None)
@click.option('--lonely', help="Do not connect to seednodes", is_flag=True)
@click.option('--network', help="Network Domain Name", type=click.STRING)
@click.option('--teacher-uri', help="An Ursula URI to start learning from (seednode)", type=click.STRING)
@click.option('--min-stake', help="The minimum stake the teacher must have to be a teacher", type=click.INT, default=0)
@click.option('--rest-host', help="The host IP address to run Ursula network services on", type=click.STRING)
@click.option('--rest-port', help="The host port to run Ursula network services on", type=NETWORK_PORT)
@click.option('--db-filepath', help="The database filepath to connect to", type=click.STRING)
@click.option('--checksum-address', help="Run with a specified account", type=EIP55_CHECKSUM_ADDRESS)
@click.option('--federated-only', '-F', help="Connect only to federated nodes", is_flag=True, default=None)
@click.option('--config-root', help="Custom configuration directory", type=click.Path())
@click.option('--config-file', help="Path to configuration file", type=EXISTING_READABLE_FILE)
@click.option('--poa', help="Inject POA middleware", is_flag=True, default=None)
@click.option('--sync/--no-sync', default=True)
@click.option('--geth', '-G', help="Run using the built-in geth node", is_flag=True)
@click.option('--provider-uri', help="Blockchain provider's URI", type=click.STRING)
@click.option('--no-registry', help="Skip importing the default contract registry", is_flag=True)
@click.option('--registry-filepath', help="Custom contract registry filepath", type=EXISTING_READABLE_FILE)
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
           sync,
           config_root,
           config_file,
           provider_uri,
           geth,
           no_registry,
           registry_filepath,
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
    # Validate
    #

    if federated_only and geth:
        raise click.BadOptionUsage(option_name="--geth", message="Federated only cannot be used with the --geth flag")

    if click_config.debug and quiet:
        raise click.BadOptionUsage(option_name="quiet", message="--debug and --quiet cannot be used at the same time.")

    # Banner
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
    # Internal Ethereum Client
    #

    ETH_NODE = NO_BLOCKCHAIN_CONNECTION
    if geth:
        ETH_NODE = actions.get_provider_process()
        provider_uri = ETH_NODE.provider_uri(scheme='file')

    #
    # Eager Actions
    #

    if action == "init":
        """Create a brand-new persistent Ursula"""

        if dev:
            raise click.BadArgumentUsage("Cannot create a persistent development character")

        if not config_root:                         # Flag
            config_root = click_config.config_file  # Envvar

        if not rest_host:
            rest_host = actions.determine_external_ip_address(force=force)

        ursula_config = UrsulaConfiguration.generate(password=get_password(confirm=True),
                                                     config_root=config_root,
                                                     rest_host=rest_host,
                                                     rest_port=rest_port,
                                                     db_filepath=db_filepath,
                                                     domains={network} if network else None,
                                                     federated_only=federated_only,
                                                     checksum_address=checksum_address,
                                                     download_registry=federated_only or no_registry,
                                                     registry_filepath=registry_filepath,
                                                     provider_process=ETH_NODE,
                                                     provider_uri=provider_uri,
                                                     poa=poa)

        painting.paint_new_installation_help(new_configuration=ursula_config)
        return

    #
    # Make Ursula
    #

    if dev:
        ursula_config = UrsulaConfiguration(dev_mode=True,
                                            domains={TEMPORARY_DOMAIN},
                                            poa=poa,
                                            download_registry=False,
                                            registry_filepath=registry_filepath,
                                            provider_process=ETH_NODE,
                                            provider_uri=provider_uri,
                                            checksum_address=checksum_address,
                                            federated_only=federated_only,
                                            rest_host=rest_host,
                                            rest_port=rest_port,
                                            db_filepath=db_filepath)
    else:
        try:
            ursula_config = UrsulaConfiguration.from_configuration_file(filepath=config_file,
                                                                        domains={network} if network else None,
                                                                        registry_filepath=registry_filepath,
                                                                        provider_process=ETH_NODE,
                                                                        provider_uri=provider_uri,
                                                                        rest_host=rest_host,
                                                                        rest_port=rest_port,
                                                                        db_filepath=db_filepath,
                                                                        poa=poa,
                                                                        federated_only=federated_only)
        except FileNotFoundError:
            return actions.handle_missing_configuration_file(character_config_class=UrsulaConfiguration,
                                                             config_file=config_file)
        except Exception as e:
            if click_config.debug:
                raise
            else:
                click.secho(str(e), fg='red', bold=True)
                raise click.Abort

    #
    # Configured Pre-Authentication Actions
    #

    # Handle destruction *before* network bootstrap and character initialization below
    if action == "destroy":
        """Delete all configuration files from the disk"""
        if dev:
            message = "'nucypher ursula destroy' cannot be used in --dev mode - There is nothing to destroy."
            raise click.BadOptionUsage(option_name='--dev', message=message)
        return actions.destroy_configuration(character_config=ursula_config, force=force)


    #
    # Make Ursula
    #

    URSULA = actions.make_cli_character(character_config=ursula_config,
                                        click_config=click_config,
                                        sync=sync,
                                        min_stake=min_stake,
                                        teacher_uri=teacher_uri,
                                        dev=dev,
                                        lonely=lonely)

    #
    # Authenticated Action Switch
    #

    if action == 'run':
        """Seed, Produce, Run!"""

        # GO!
        try:

            # Ursula Deploy Warnings
            click_config.emit(
                message="Starting Ursula on {}".format(URSULA.rest_interface),
                color='green',
                bold=True)

            click_config.emit(
                message="Connecting to {}".format(','.join(ursula_config.domains)),
                color='green',
                bold=True)

            if not URSULA.federated_only and URSULA.stakes:
                click_config.emit(
                    message=f"Staking {str(URSULA.current_stake)} ~ Keep Ursula Online!",
                    color='blue',
                    bold=True)

            if not click_config.debug:
                stdio.StandardIO(UrsulaCommandProtocol(ursula=URSULA))

            if dry_run:
                return  # <-- ABORT - (Last Chance)

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

        # Graceful Exit
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

        if not URSULA.federated_only:
            click.secho("BLOCKCHAIN ----------\n")
            painting.paint_contract_status(click_config=click_config, ursula_config=ursula_config)
            current_block = URSULA.blockchain.w3.eth.blockNumber
            click.secho(f'Block # {current_block}')
            click.secho(f'NU Balance: {URSULA.token_balance}')
            click.secho(f'ETH Balance: {URSULA.eth_balance}')
            click.secho(f'Current Gas Price {URSULA.blockchain.client.gasPrice}')

        click.secho("CONFIGURATION --------")
        response = UrsulaConfiguration._read_configuration_file(filepath=config_file or ursula_config.config_file_location)
        return click_config.emit(response=response)

    elif action == "forget":
        actions.forget(configuration=ursula_config)
        return

    elif action == 'confirm-activity':
        if not URSULA.stakes:
            click.secho("There are no active stakes for {}".format(URSULA.checksum_address))
            return
        URSULA.staking_agent.confirm_activity(node_address=URSULA.checksum_address)
        return

    else:
        raise click.BadArgumentUsage("No such argument {}".format(action))
