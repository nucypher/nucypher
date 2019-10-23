import functools
import json

import click

from nucypher.characters.banners import BOB_BANNER
from nucypher.cli import actions, painting
from nucypher.cli.actions import get_nucypher_password, select_client_account
from nucypher.cli.common_options import (
    group_options,
    option_checksum_address,
    option_config_file,
    option_config_root,
    option_controller_port,
    option_dev,
    option_discovery_port,
    option_dry_run,
    option_federated_only,
    option_force,
    option_label,
    option_message_kit,
    option_min_stake,
    option_network,
    option_policy_encrypting_key,
    option_provider_uri,
    option_registry_filepath,
    option_teacher_uri,
    )
from nucypher.cli.config import group_general_config
from nucypher.cli.types import NETWORK_PORT, EXISTING_READABLE_FILE, EIP55_CHECKSUM_ADDRESS
from nucypher.config.characters import BobConfiguration
from nucypher.config.constants import DEFAULT_CONFIG_ROOT
from nucypher.crypto.powers import DecryptingPower
from nucypher.utilities.sandbox.constants import TEMPORARY_DOMAIN


group_admin = group_options(
    'admin',
    provider_uri=option_provider_uri(),
    network=option_network,
    registry_filepath=option_registry_filepath,
    checksum_address=option_checksum_address,
    )


group_api = group_options(
    'api',
    admin=group_admin,
    dev=option_dev,
    config_file=option_config_file,
    discovery_port=option_discovery_port(),
    teacher_uri=option_teacher_uri,
    min_stake=option_min_stake,
    )


@click.group()
def bob():
    """
    "Bob the Data Recipient" management commands.
    """
    pass


@bob.command()
@group_admin
@option_federated_only
@option_config_root
@group_general_config
def init(general_config,

         # Admin Options
         admin,

         # Other
         federated_only, config_root):

    """
    Create a brand new persistent Bob.
    """
    emitter = _setup_emitter(general_config)

    if not config_root:  # Flag
        config_root = general_config.config_file  # Envvar

    checksum_address = admin.checksum_address
    if not checksum_address and not federated_only:
        checksum_address = select_client_account(emitter=emitter, provider_uri=admin.provider_uri)

    new_bob_config = BobConfiguration.generate(password=get_nucypher_password(confirm=True),
                                               config_root=config_root or DEFAULT_CONFIG_ROOT,
                                               checksum_address=checksum_address,
                                               domains={admin.network} if admin.network else None,
                                               federated_only=federated_only,
                                               registry_filepath=admin.registry_filepath,
                                               provider_uri=admin.provider_uri)
    return painting.paint_new_installation_help(emitter, new_configuration=new_bob_config)


@bob.command()
@group_api
@option_controller_port(default=BobConfiguration.DEFAULT_CONTROLLER_PORT)
@option_dry_run
@group_general_config
def run(general_config,

        # API Options
        api,

        # Other
        controller_port, dry_run):
    """
    Start Bob's controller.
    """

    ### Setup ###
    emitter = _setup_emitter(general_config)

    admin = api.admin

    bob_config = _get_bob_config(
        general_config, api.dev, admin.provider_uri, admin.network, admin.registry_filepath, admin.checksum_address,
        api.config_file, api.discovery_port)
    #############

    BOB = actions.make_cli_character(character_config=bob_config,
                                     general_config=general_config,
                                     unlock_keyring=not api.dev,
                                     teacher_uri=api.teacher_uri,
                                     min_stake=api.min_stake)

    # RPC
    if general_config.json_ipc:
        rpc_controller = BOB.make_rpc_controller()
        _transport = rpc_controller.make_control_transport()
        rpc_controller.start()
        return

    # Echo Public Keys
    emitter.message(f"Bob Verifying Key {bytes(BOB.stamp).hex()}", color='green', bold=True)
    bob_encrypting_key = bytes(BOB.public_keys(DecryptingPower)).hex()
    emitter.message(f"Bob Encrypting Key {bob_encrypting_key}", color="blue", bold=True)
    # Start Controller
    controller = BOB.make_web_controller(crash_on_error=general_config.debug)
    BOB.log.info('Starting HTTP Character Web Controller')
    return controller.start(http_port=controller_port, dry_run=dry_run)


@bob.command()
@group_api
@group_general_config
def view(general_config,

         # API Options
         api
         ):
    """
    View existing Bob's configuration.
    """

    ### Setup ###
    emitter = _setup_emitter(general_config)

    admin = api.admin

    bob_config = _get_bob_config(
        general_config, api.dev, admin.provider_uri, admin.network, admin.registry_filepath, admin.checksum_address,
        api.config_file, api.discovery_port)

    #############

    filepath = api.config_file or bob_config.config_file_location
    emitter.echo(f"Bob Configuration {filepath} \n {'='*55}")
    response = BobConfiguration._read_configuration_file(filepath=filepath)
    return emitter.echo(json.dumps(response, indent=4))


@bob.command()
@group_admin
@option_dev
@option_config_file
@option_discovery_port()
@option_force
@group_general_config
def destroy(general_config,

            # Admin Options
            admin,

            # Other
            dev, config_file, discovery_port, force
            ):
    """
    Delete existing Bob's configuration.
    """
    ### Setup ###
    emitter = _setup_emitter(general_config)

    bob_config = _get_bob_config(
        general_config, dev, admin.provider_uri, admin.network, admin.registry_filepath, admin.checksum_address,
        config_file, discovery_port)

    #############

    # Validate
    if dev:
        message = "'nucypher bob destroy' cannot be used in --dev mode"
        raise click.BadOptionUsage(option_name='--dev', message=message)

    # Request
    return actions.destroy_configuration(emitter, character_config=bob_config, force=force)


@bob.command(name='public-keys')
@group_api
@group_general_config
def public_keys(general_config,

                # API Options
                api
                ):
    """
    Obtain Bob's public verification and encryption keys.
    """

    ### Setup ###
    _setup_emitter(general_config)

    admin = api.admin

    bob_config = _get_bob_config(
        general_config, api.dev, admin.provider_uri, admin.network, admin.registry_filepath, admin.checksum_address,
        api.config_file, api.discovery_port)

    #############

    BOB = actions.make_cli_character(character_config=bob_config,
                                     general_config=general_config,
                                     unlock_keyring=not api.dev,
                                     teacher_uri=api.teacher_uri,
                                     min_stake=api.min_stake,
                                     load_preferred_teachers=False,
                                     start_learning_now=False)

    response = BOB.controller.public_keys()
    return response


@bob.command()
@group_api
@option_label()
@option_policy_encrypting_key()
@click.option('--alice-verifying-key', help="Alice's verifying key as a hexadecimal string", type=click.STRING)
@option_message_kit()
@group_general_config
def retrieve(general_config,

             # API Options
             api,

             # Other
             label, policy_encrypting_key, alice_verifying_key, message_kit):
    """
    Obtain plaintext from encrypted data, if access was granted.
    """

    ### Setup ###
    _setup_emitter(general_config)

    admin = api.admin

    bob_config = _get_bob_config(
        general_config, api.dev, admin.provider_uri, admin.network, admin.registry_filepath, admin.checksum_address,
        api.config_file, api.discovery_port)

    #############

    BOB = actions.make_cli_character(character_config=bob_config,
                                     general_config=general_config,
                                     unlock_keyring=not api.dev,
                                     teacher_uri=api.teacher_uri,
                                     min_stake=api.min_stake)

    # Validate
    if not all((label, policy_encrypting_key, alice_verifying_key, message_kit)):
        input_specification, output_specification = BOB.control.get_specifications(interface_name='retrieve')
        required_fields = ', '.join(input_specification)
        raise click.BadArgumentUsage(f'{required_fields} are required flags to retrieve')

    # Request
    bob_request_data = {
        'label': label,
        'policy_encrypting_key': policy_encrypting_key,
        'alice_verifying_key': alice_verifying_key,
        'message_kit': message_kit,
    }

    response = BOB.controller.retrieve(request=bob_request_data)
    return response


def _get_bob_config(general_config, dev, provider_uri, network, registry_filepath, checksum_address, config_file,
                    discovery_port):
    if dev:
        bob_config = BobConfiguration(dev_mode=True,
                                      domains={TEMPORARY_DOMAIN},
                                      provider_uri=provider_uri,
                                      federated_only=True,
                                      checksum_address=checksum_address,
                                      network_middleware=general_config.middleware)
    else:

        try:
            bob_config = BobConfiguration.from_configuration_file(
                filepath=config_file,
                domains={network} if network else None,
                checksum_address=checksum_address,
                rest_port=discovery_port,
                provider_uri=provider_uri,
                registry_filepath=registry_filepath,
                network_middleware=general_config.middleware)
        except FileNotFoundError:
            return actions.handle_missing_configuration_file(character_config_class=BobConfiguration,
                                                             config_file=config_file)

    return bob_config


def _setup_emitter(general_config):
    # Banner
    emitter = general_config.emitter
    emitter.clear()
    emitter.banner(BOB_BANNER)

    return emitter
