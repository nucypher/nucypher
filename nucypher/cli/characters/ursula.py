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
import functools
import json

import click
from constant_sorrow.constants import NO_BLOCKCHAIN_CONNECTION
from twisted.internet import stdio

from nucypher.blockchain.economics import TokenEconomicsFactory
from nucypher.blockchain.eth.utils import datetime_at_period
from nucypher.characters.banners import URSULA_BANNER
from nucypher.cli import actions, painting
from nucypher.cli.actions import (
    get_nucypher_password,
    select_client_account,
    get_client_password
)
from nucypher.cli.common_options import (
    group_options,
    option_config_file,
    option_config_root,
    option_db_filepath,
    option_dev,
    option_dry_run,
    option_federated_only,
    option_force,
    option_geth,
    option_light,
    option_min_stake,
    option_network,
    option_poa,
    option_provider_uri,
    option_registry_filepath,
    option_teacher_uri,
    )
from nucypher.cli.config import group_general_config
from nucypher.cli.processes import UrsulaCommandProtocol
from nucypher.cli.types import (
    EIP55_CHECKSUM_ADDRESS,
    NETWORK_PORT,
    EXISTING_READABLE_FILE
)
from nucypher.config.characters import UrsulaConfiguration
from nucypher.config.keyring import NucypherKeyring
from nucypher.utilities.sandbox.constants import (
    TEMPORARY_DOMAIN,
)


group_admin = group_options(
    'admin',
    geth=option_geth,
    provider_uri=option_provider_uri(),
    network=option_network,
    registry_filepath=option_registry_filepath,
    staker_address=click.option('--staker-address', help="Run on behalf of a specified staking account", type=EIP55_CHECKSUM_ADDRESS),
    worker_address=click.option('--worker-address', help="Run the worker-ursula with a specified address",
                  type=EIP55_CHECKSUM_ADDRESS),
    federated_only=option_federated_only,
    rest_host=click.option('--rest-host', help="The host IP address to run Ursula network services on", type=click.STRING),
    rest_port=click.option('--rest-port', help="The host port to run Ursula network services on", type=NETWORK_PORT),
    db_filepath=option_db_filepath,
    poa=option_poa,
    light=option_light,
    )


# Args (geth, provider_uri, network, registry_filepath, staker_address, worker_address, federated_only, rest_host,
#       rest_port, db_filepath, poa, config_file, dev, lonely, teacher_uri, min_stake)
group_api = group_options(
    'api',
    admin=group_admin,
    config_file=option_config_file,
    dev=option_dev,
    lonely=click.option('--lonely', help="Do not connect to seednodes", is_flag=True),
    teacher_uri=option_teacher_uri,
    min_stake=option_min_stake,
    )

@click.group()
def ursula():
    """
    "Ursula the Untrusted" PRE Re-encryption node management commands.
    """

    pass


@ursula.command()
@group_admin
@option_force
@option_config_root
@group_general_config
def init(general_config,

         # Admin Options
         admin,

         # Other
         force, config_root):
    """
    Create a new Ursula node configuration.
    """

    ### Setup ###
    _validate_args(admin.geth, admin.federated_only, admin.staker_address, admin.registry_filepath)

    emitter = _setup_emitter(general_config, admin.worker_address)

    _pre_launch_warnings(emitter, dev=None, force=force)

    ETH_NODE = NO_BLOCKCHAIN_CONNECTION
    provider_uri = admin.provider_uri
    if admin.geth:
        ETH_NODE = actions.get_provider_process()
        provider_uri = ETH_NODE.provider_uri(scheme='file')
    #############

    staker_address = admin.staker_address
    worker_address = admin.worker_address
    if (not staker_address or not worker_address) and not admin.federated_only:
        if not staker_address:
            staker_address = click.prompt("Enter staker address", type=EIP55_CHECKSUM_ADDRESS)

        if not worker_address:
            prompt = "Select worker account"
            worker_address = select_client_account(emitter=emitter, prompt=prompt, provider_uri=provider_uri)
    if not config_root:  # Flag
        config_root = general_config.config_file  # Envvar

    rest_host = admin.rest_host
    if not rest_host:
        rest_host = actions.determine_external_ip_address(emitter, force=force)
    ursula_config = UrsulaConfiguration.generate(password=get_nucypher_password(confirm=True),
                                                 config_root=config_root,
                                                 rest_host=rest_host,
                                                 rest_port=admin.rest_port,
                                                 db_filepath=admin.db_filepath,
                                                 domains={admin.network} if admin.network else None,
                                                 federated_only=admin.federated_only,
                                                 checksum_address=staker_address,
                                                 worker_address=worker_address,
                                                 registry_filepath=admin.registry_filepath,
                                                 provider_process=ETH_NODE,
                                                 provider_uri=provider_uri,
                                                 poa=admin.poa,
                                                 light=admin.light)
    painting.paint_new_installation_help(emitter, new_configuration=ursula_config)


@ursula.command()
@group_admin
@option_config_file
@option_dev
@option_force
@group_general_config
def destroy(general_config,

            # Admin Options
            admin,

            # Other
            config_file, force, dev):
    """
    Delete Ursula node configuration.
    """

    ### Setup ###
    _validate_args(admin.geth, admin.federated_only, admin.staker_address, admin.registry_filepath)

    emitter = _setup_emitter(general_config, admin.worker_address)

    _pre_launch_warnings(emitter, dev=dev, force=force)

    ursula_config, provider_uri = _get_ursula_config(
        emitter, admin.geth, admin.provider_uri, admin.network, admin.registry_filepath, dev,
        config_file, admin.staker_address, admin.worker_address, admin.federated_only,
        admin.rest_host, admin.rest_port, admin.db_filepath, admin.poa, admin.light)
    #############

    actions.destroy_configuration(emitter, character_config=ursula_config, force=force)


@ursula.command()
@group_admin
@option_config_file
@option_dev
@group_general_config
def forget(general_config,

           # Admin Options
           admin,

           # Other
           config_file,  dev):
    """
    Forget all known nodes.
    """
    ### Setup ###
    _validate_args(admin.geth, admin.federated_only, admin.staker_address, admin.registry_filepath)

    emitter = _setup_emitter(general_config, admin.worker_address)

    _pre_launch_warnings(emitter, dev=dev, force=None)

    ursula_config, provider_uri = _get_ursula_config(
        emitter, admin.geth, admin.provider_uri, admin.network, admin.registry_filepath, dev,
        config_file, admin.staker_address, admin.worker_address, admin.federated_only,
        admin.rest_host, admin.rest_port, admin.db_filepath, admin.poa, admin.light)

    #############

    actions.forget(emitter, configuration=ursula_config)


@ursula.command()
@group_api
@click.option('--interactive', '-I', help="Launch command interface after connecting to seednodes.", is_flag=True,
              default=False)
@option_dry_run
@group_general_config
def run(general_config,

        # API Options
        api,

        # Other
        interactive, dry_run):
    """
    Run an "Ursula" node.
    """

    ### Setup ###
    admin = api.admin
    _validate_args(admin.geth, admin.federated_only, admin.staker_address, admin.registry_filepath)

    emitter = _setup_emitter(general_config, admin.worker_address)

    _pre_launch_warnings(emitter, dev=api.dev, force=None)

    ursula_config, provider_uri = _get_ursula_config(
        emitter, admin.geth, admin.provider_uri, admin.network, admin.registry_filepath, api.dev,
        api.config_file, admin.staker_address, admin.worker_address, admin.federated_only,
        admin.rest_host, admin.rest_port, admin.db_filepath, admin.poa, admin.light)

    #############

    URSULA = _create_ursula(ursula_config, general_config, api.dev, emitter, api.lonely, api.teacher_uri, api.min_stake)

    # GO!
    try:

        # Ursula Deploy Warnings
        emitter.message(
            f"Starting Ursula on {URSULA.rest_interface}",
            color='green',
            bold=True)

        emitter.message(
            f"Connecting to {','.join(ursula_config.domains)}",
            color='green',
            bold=True)

        emitter.message(
            "Working ~ Keep Ursula Online!",
            color='blue',
            bold=True)

        if interactive:
            stdio.StandardIO(UrsulaCommandProtocol(ursula=URSULA, emitter=emitter))

        if dry_run:
            return  # <-- ABORT - (Last Chance)

        # Run - Step 3
        node_deployer = URSULA.get_deployer()
        node_deployer.addServices()
        node_deployer.catalogServers(node_deployer.hendrix)
        node_deployer.run()  # <--- Blocking Call (Reactor)

    # Handle Crash
    except Exception as e:
        ursula_config.log.critical(str(e))
        emitter.message(
            f"{e.__class__.__name__} {e}",
            color='red',
            bold=True)
        raise  # Crash :-(

    # Graceful Exit
    finally:
        emitter.message("Stopping Ursula", color='green')
        ursula_config.cleanup()
        emitter.message("Ursula Stopped", color='red')


@ursula.command(name='save-metadata')
@group_api
@group_general_config
def save_metadata(general_config,

                  # API Options
                  api
                  ):
    """
    Manually write node metadata to disk without running.
    """
    ### Setup ###
    admin = api.admin
    _validate_args(admin.geth, admin.federated_only, admin.staker_address, admin.registry_filepath)

    emitter = _setup_emitter(general_config, admin.worker_address)

    _pre_launch_warnings(emitter, dev=api.dev, force=None)

    ursula_config, provider_uri = _get_ursula_config(
        emitter, admin.geth, admin.provider_uri, admin.network, admin.registry_filepath, api.dev,
        api.config_file, admin.staker_address, admin.worker_address, admin.federated_only,
        admin.rest_host, admin.rest_port, admin.db_filepath, admin.poa, admin.light)

    #############

    URSULA = _create_ursula(ursula_config, general_config, api.dev, emitter, api.lonely,
                            api.teacher_uri, api.min_stake, load_seednodes=False)

    metadata_path = URSULA.write_node_metadata(node=URSULA)
    emitter.message(f"Successfully saved node metadata to {metadata_path}.", color='green')


@ursula.command()
@group_api
@group_general_config
def view(general_config,

         # API Options
         api,
         ):
    """
    View the Ursula node's configuration.
    """

    ### Setup ###
    admin = api.admin
    _validate_args(admin.geth, admin.federated_only, admin.staker_address, admin.registry_filepath)

    emitter = _setup_emitter(general_config, admin.worker_address)

    _pre_launch_warnings(emitter, dev=api.dev, force=None)

    ursula_config, provider_uri = _get_ursula_config(
        emitter, admin.geth, admin.provider_uri, admin.network, admin.registry_filepath, api.dev,
        api.config_file, admin.staker_address, admin.worker_address, admin.federated_only,
        admin.rest_host, admin.rest_port, admin.db_filepath, admin.poa, admin.light)

    #############

    filepath = api.config_file or ursula_config.config_file_location
    emitter.echo(f"Ursula Configuration {filepath} \n {'='*55}")
    response = UrsulaConfiguration._read_configuration_file(filepath=filepath)
    return emitter.echo(json.dumps(response, indent=4))


@ursula.command(name='confirm-activity')
@group_api
@group_general_config
def confirm_activity(general_config,

                     # API Options
                     api
                     ):
    """
    Manually confirm-activity for the current period.
    """

    ### Setup ###
    admin = api.admin
    _validate_args(admin.geth, admin.federated_only, admin.staker_address, admin.registry_filepath)

    emitter = _setup_emitter(general_config, admin.worker_address)

    _pre_launch_warnings(emitter, dev=api.dev, force=None)

    ursula_config, provider_uri = _get_ursula_config(
        emitter, admin.geth, admin.provider_uri, admin.network, admin.registry_filepath, api.dev,
        api.config_file, admin.staker_address, admin.worker_address, admin.federated_only,
        admin.rest_host, admin.rest_port, admin.db_filepath, admin.poa, admin.light)

    #############

    URSULA = _create_ursula(ursula_config, general_config, api.dev, emitter,
                            api.lonely, api.teacher_uri, api.min_stake, load_seednodes=False)

    confirmed_period = URSULA.staking_agent.get_current_period() + 1
    click.echo(f"Confirming activity for period {confirmed_period}", color='blue')
    receipt = URSULA.confirm_activity()

    economics = TokenEconomicsFactory.get_economics(registry=URSULA.registry)
    date = datetime_at_period(period=confirmed_period,
                              seconds_per_period=economics.seconds_per_period)

    # TODO: Double-check dates here
    emitter.echo(f'\nActivity confirmed for period #{confirmed_period} '
                 f'(starting at {date})', bold=True, color='blue')
    painting.paint_receipt_summary(emitter=emitter,
                                   receipt=receipt,
                                   chain_name=URSULA.staking_agent.blockchain.client.chain_name)

    # TODO: Check ActivityConfirmation event (see #1193)


def _setup_emitter(general_config, worker_address):
    # Banner
    emitter = general_config.emitter
    emitter.clear()
    emitter.banner(URSULA_BANNER.format(worker_address or ''))

    return emitter


def _validate_args(geth, federated_only, staker_address, registry_filepath):
    #
    # Validate
    #
    if federated_only:
        # TODO: consider rephrasing in a more universal voice.
        if geth:
            raise click.BadOptionUsage(option_name="--geth",
                                       message="--geth cannot be used in federated mode.")

        if staker_address:
            raise click.BadOptionUsage(option_name='--staker-address',
                                       message="--staker-address cannot be used in federated mode.")

        if registry_filepath:
            raise click.BadOptionUsage(option_name="--registry-filepath",
                                       message=f"--registry-filepath cannot be used in federated mode.")


def _pre_launch_warnings(emitter, dev, force):
    if dev:
        emitter.echo("WARNING: Running in Development mode", color='yellow', verbosity=1)
    if force:
        emitter.echo("WARNING: Force is enabled", color='yellow', verbosity=1)


def _get_ursula_config(emitter, geth, provider_uri, network, registry_filepath, dev, config_file,
                       staker_address, worker_address, federated_only, rest_host, rest_port, db_filepath, poa, light):

    ETH_NODE = NO_BLOCKCHAIN_CONNECTION
    if geth:
        ETH_NODE = actions.get_provider_process()
        provider_uri = ETH_NODE.provider_uri(scheme='file')

    if dev:
        ursula_config = UrsulaConfiguration(dev_mode=True,
                                            domains={TEMPORARY_DOMAIN},
                                            poa=poa,
                                            light=light,
                                            registry_filepath=registry_filepath,
                                            provider_process=ETH_NODE,
                                            provider_uri=provider_uri,
                                            checksum_address=staker_address,
                                            worker_address=worker_address,
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
                                                                        light=light,
                                                                        federated_only=federated_only)
        except FileNotFoundError:
            return actions.handle_missing_configuration_file(character_config_class=UrsulaConfiguration,
                                                             config_file=config_file)
        except NucypherKeyring.AuthenticationFailed as e:
            emitter.echo(str(e), color='red', bold=True)
            # TODO: Exit codes (not only for this, but for other exceptions)
            return click.get_current_context().exit(1)

    return ursula_config, provider_uri


def _create_ursula(ursula_config, general_config, dev, emitter, lonely, teacher_uri, min_stake, load_seednodes=True):
    #
    # Make Ursula
    #

    client_password = None
    if not ursula_config.federated_only:
        if not dev and not general_config.json_ipc:
            client_password = get_client_password(checksum_address=ursula_config.worker_address,
                                                  envvar="NUCYPHER_WORKER_ETH_PASSWORD")

    try:
        URSULA = actions.make_cli_character(character_config=ursula_config,
                                            general_config=general_config,
                                            min_stake=min_stake,
                                            teacher_uri=teacher_uri,
                                            unlock_keyring=not dev,
                                            lonely=lonely,
                                            client_password=client_password,
                                            load_preferred_teachers=load_seednodes,
                                            start_learning_now=load_seednodes)

        return URSULA
    except NucypherKeyring.AuthenticationFailed as e:
        emitter.echo(str(e), color='red', bold=True)
        # TODO: Exit codes (not only for this, but for other exceptions)
        return click.get_current_context().exit(1)
