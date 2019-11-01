import functools
import json

import click
from constant_sorrow.constants import NO_BLOCKCHAIN_CONNECTION

from nucypher.characters.banners import ALICE_BANNER
from nucypher.cli import actions, painting, types
from nucypher.cli.actions import get_nucypher_password, select_client_account, get_client_password
from nucypher.cli.common_options import (
    group_options,
    option_config_file,
    option_config_root,
    option_controller_port,
    option_dev,
    option_discovery_port,
    option_dry_run,
    option_federated_only,
    option_force,
    option_geth,
    option_hw_wallet,
    option_label,
    option_light,
    option_m,
    option_message_kit,
    option_min_stake,
    option_n,
    option_network,
    option_poa,
    option_provider_uri,
    option_registry_filepath,
    option_teacher_uri,
    )
from nucypher.cli.config import group_general_config
from nucypher.cli.types import NETWORK_PORT, EXISTING_READABLE_FILE, EIP55_CHECKSUM_ADDRESS
from nucypher.config.characters import AliceConfiguration
from nucypher.config.keyring import NucypherKeyring
from nucypher.utilities.sandbox.constants import TEMPORARY_DOMAIN


option_bob_verifying_key = click.option(
    '--bob-verifying-key', help="Bob's verifying key as a hexadecimal string", type=click.STRING,
    required=True)


group_admin = group_options(
    'admin',
    geth=option_geth,
    provider_uri=option_provider_uri(),
    federated_only=option_federated_only,
    dev=option_dev,
    pay_with=click.option('--pay-with', help="Run with a specified account", type=EIP55_CHECKSUM_ADDRESS),
    network=option_network,
    registry_filepath=option_registry_filepath)


group_api = group_options(
    'api',
    admin=group_admin,
    config_file=option_config_file,
    discovery_port=option_discovery_port(),
    hw_wallet=option_hw_wallet,
    teacher_uri=option_teacher_uri,
    min_stake=option_min_stake,
    )


@click.group()
def alice():
    """
    "Alice the Policy Authority" management commands.
    """
    pass


@alice.command()
@group_admin
@option_config_root
@option_poa
@option_light
@option_m
@option_n
@click.option('--rate', help="Policy rate per period in wei", type=click.FLOAT)
@click.option('--duration-periods', help="Policy duration in periods", type=click.FLOAT)
@group_general_config
def init(general_config,

         # Admin Options
         admin,

         # Other
         config_root, poa, light, m, n, rate, duration_periods):
    """
    Create a brand new persistent Alice.
    """

    ### Setup ###
    emitter = _setup_emitter(general_config)

    if admin.federated_only and admin.geth:
        raise click.BadOptionUsage(option_name="--geth", message="Federated only cannot be used with the --geth flag")

    #
    # Managed Ethereum Client
    #

    ETH_NODE = NO_BLOCKCHAIN_CONNECTION
    provider_uri = admin.provider_uri
    if admin.geth:
        ETH_NODE = actions.get_provider_process()
        provider_uri = ETH_NODE.provider_uri(scheme='file')

    #############

    if admin.dev:
        raise click.BadArgumentUsage("Cannot create a persistent development character")

    if not provider_uri and not admin.federated_only:
        raise click.BadOptionUsage(option_name='--provider',
                                   message="--provider is required to create a new decentralized alice.")

    if not config_root:  # Flag
        config_root = general_config.config_file  # Envvar

    pay_with = admin.pay_with
    if not pay_with and not admin.federated_only:
        pay_with = select_client_account(emitter=emitter, provider_uri=provider_uri)

    new_alice_config = AliceConfiguration.generate(password=get_nucypher_password(confirm=True),
                                                   config_root=config_root,
                                                   checksum_address=pay_with,
                                                   domains={admin.network} if admin.network else None,
                                                   federated_only=admin.federated_only,
                                                   registry_filepath=admin.registry_filepath,
                                                   provider_process=ETH_NODE,
                                                   poa=poa,
                                                   light=light,
                                                   provider_uri=provider_uri,
                                                   m=m,
                                                   n=n,
                                                   duration_periods=duration_periods,
                                                   rate=rate)

    painting.paint_new_installation_help(emitter, new_configuration=new_alice_config)


@alice.command()
@option_config_file
@group_general_config
def view(general_config, config_file):
    """
    View existing Alice's configuration.
    """
    emitter = _setup_emitter(general_config)
    configuration_file_location = config_file or AliceConfiguration.default_filepath()
    response = AliceConfiguration._read_configuration_file(filepath=configuration_file_location)
    emitter.echo(f"Alice Configuration {configuration_file_location} \n {'='*55}")
    return emitter.echo(json.dumps(response, indent=4))


@alice.command()
@group_admin
@option_config_file
@option_discovery_port()
@option_force
@group_general_config
def destroy(general_config,

            # Admin Options
            admin,

            # Other
            config_file, discovery_port, force):
    """
    Delete existing Alice's configuration.
    """
    ### Setup ###
    emitter = _setup_emitter(general_config)

    alice_config, provider_uri = _get_alice_config(
        general_config, config_file, admin.dev, discovery_port, admin.federated_only,
        admin.geth, admin.network, admin.pay_with, admin.provider_uri, admin.registry_filepath)
    #############

    if admin.dev:
        message = "'nucypher alice destroy' cannot be used in --dev mode"
        raise click.BadOptionUsage(option_name='--dev', message=message)
    return actions.destroy_configuration(emitter, character_config=alice_config, force=force)


@alice.command()
@group_api
@option_controller_port(default=AliceConfiguration.DEFAULT_CONTROLLER_PORT)
@option_dry_run
@group_general_config
def run(general_config,

        # API Options
        api,

        # Other
        controller_port, dry_run):
    """
    Start Alice's controller.
    """

    ### Setup ###
    emitter = _setup_emitter(general_config)

    admin = api.admin

    alice_config, provider_uri = _get_alice_config(
        general_config, api.config_file, admin.dev, api.discovery_port, admin.federated_only,
        admin.geth, admin.network, admin.pay_with, admin.provider_uri, admin.registry_filepath)
    #############

    ALICE = _create_alice(alice_config, general_config, admin.dev, emitter, api.hw_wallet, api.teacher_uri, api.min_stake)

    try:
        # RPC
        if general_config.json_ipc:
            rpc_controller = ALICE.make_rpc_controller()
            _transport = rpc_controller.make_control_transport()
            rpc_controller.start()
            return

        # HTTP
        else:
            emitter.message(f"Alice Verifying Key {bytes(ALICE.stamp).hex()}", color="green", bold=True)
            controller = ALICE.make_web_controller(crash_on_error=general_config.debug)
            ALICE.log.info('Starting HTTP Character Web Controller')
            emitter.message(f'Running HTTP Alice Controller at http://localhost:{controller_port}')
            return controller.start(http_port=controller_port, dry_run=dry_run)

    # Handle Crash
    except Exception as e:
        alice_config.log.critical(str(e))
        emitter.message(f"{e.__class__.__name__} {e}", color='red', bold=True)
        if general_config.debug:
            raise  # Crash :-(


@alice.command("public-keys")
@group_api
@group_general_config
def public_keys(general_config, api):
    """
    Obtain Alice's public verification and encryption keys.
    """

    ### Setup ###
    emitter = _setup_emitter(general_config)

    admin = api.admin

    alice_config, _ = _get_alice_config(
        general_config, api.config_file, admin.dev, api.discovery_port, admin.federated_only,
        admin.geth, admin.network, admin.pay_with, admin.provider_uri, admin.registry_filepath)
    #############

    ALICE = _create_alice(alice_config, general_config, admin.dev,
                          emitter, api.hw_wallet, api.teacher_uri, api.min_stake, load_seednodes=False)

    response = ALICE.controller.public_keys()
    return response


@alice.command('derive-policy-pubkey')
@option_label(required=True)
@group_api
@group_general_config
def derive_policy_pubkey(general_config, label, api):
    """
    Get a policy public key from a policy label.
    """
    ### Setup ###
    emitter = _setup_emitter(general_config)

    admin = api.admin

    alice_config, _ = _get_alice_config(
        general_config, api.config_file, admin.dev, api.discovery_port, admin.federated_only,
        admin.geth, admin.network, admin.pay_with, admin.provider_uri, admin.registry_filepath)
    #############

    ALICE = _create_alice(alice_config, general_config, admin.dev,
                          emitter, api.hw_wallet, api.teacher_uri, api.min_stake, load_seednodes=False)

    # Request
    return ALICE.controller.derive_policy_encrypting_key(label=label)


@alice.command()
@click.option('--bob-encrypting-key', help="Bob's encrypting key as a hexadecimal string", type=click.STRING,
              required=True)
@option_bob_verifying_key
@option_label(required=True)
@option_m
@option_n
@click.option('--expiration', help="Expiration Datetime of a policy", type=click.STRING)  # TODO: click.DateTime()
@click.option('--value', help="Total policy value (in Wei)", type=types.WEI)
@group_api
@group_general_config
def grant(general_config,
          # Other (required)
          bob_encrypting_key, bob_verifying_key, label,

          # Other
          m, n, expiration, value,

          # API Options
          api
          ):
    """
    Create and enact an access policy for some Bob.
    """
    ### Setup ###
    emitter = _setup_emitter(general_config)

    admin = api.admin

    alice_config, _ = _get_alice_config(
        general_config, api.config_file, admin.dev, api.discovery_port, admin.federated_only,
        admin.geth, admin.network, admin.pay_with, admin.provider_uri, admin.registry_filepath)

    #############

    ALICE = _create_alice(alice_config, general_config, admin.dev, emitter, api.hw_wallet, api.teacher_uri, api.min_stake)

    # Request
    grant_request = {
        'bob_encrypting_key': bob_encrypting_key,
        'bob_verifying_key': bob_verifying_key,
        'label': label,
        'm': m,
        'n': n,
        'expiration': expiration,
    }

    if not ALICE.federated_only:
        grant_request.update({'value': value})
    return ALICE.controller.grant(request=grant_request)


@alice.command()
@option_bob_verifying_key
@option_label(required=True)
@group_api
@group_general_config
def revoke(general_config,

           # Other (required)
           bob_verifying_key, label,

           # API Options
           api
           ):
    """
    Revoke a policy.
    """
    ### Setup ###
    emitter = _setup_emitter(general_config)

    admin = api.admin

    alice_config, _ = _get_alice_config(
        general_config, api.config_file, admin.dev, api.discovery_port, admin.federated_only,
        admin.geth, admin.network, admin.pay_with, admin.provider_uri, admin.registry_filepath)

    #############

    ALICE = _create_alice(alice_config, general_config, admin.dev, emitter, api.hw_wallet, api.teacher_uri, api.min_stake)

    # Request
    revoke_request = {'label': label, 'bob_verifying_key': bob_verifying_key}
    return ALICE.controller.revoke(request=revoke_request)


@alice.command()
@option_label(required=True)
@option_message_kit(required=True)
@group_api
@group_general_config
def decrypt(general_config,

            # Other (required)
            label, message_kit,

            # API Options
            api
            ):
    """
    Decrypt data encrypted under an Alice's policy public key.
    """
    ### Setup ###
    emitter = _setup_emitter(general_config)

    admin = api.admin

    alice_config, _ = _get_alice_config(
        general_config, api.config_file, admin.dev, api.discovery_port, admin.federated_only,
        admin.geth, admin.network, admin.pay_with, admin.provider_uri, admin.registry_filepath)

    #############

    ALICE = _create_alice(alice_config, general_config, admin.dev, emitter,
                          api.hw_wallet, api.teacher_uri, api.min_stake, load_seednodes=False)

    # Request
    request_data = {'label': label, 'message_kit': message_kit}
    response = ALICE.controller.decrypt(request=request_data)
    return response


def _setup_emitter(general_config):
    # Banner
    emitter = general_config.emitter
    emitter.clear()
    emitter.banner(ALICE_BANNER)

    return emitter


def _get_alice_config(general_config, config_file, dev, discovery_port, federated_only, geth, network, pay_with,
                      provider_uri, registry_filepath):
    if federated_only and geth:
        raise click.BadOptionUsage(option_name="--geth", message="Federated only cannot be used with the --geth flag")
    #
    # Managed Ethereum Client
    #
    ETH_NODE = NO_BLOCKCHAIN_CONNECTION
    if geth:
        ETH_NODE = actions.get_provider_process()
        provider_uri = ETH_NODE.provider_uri(scheme='file')

    # Get config
    alice_config = _get_or_create_alice_config(general_config, dev, network, ETH_NODE, provider_uri,
                                               config_file, discovery_port, pay_with, registry_filepath)
    return alice_config, provider_uri


def _get_or_create_alice_config(general_config, dev, network, eth_node, provider_uri, config_file,
                                discovery_port, pay_with, registry_filepath):
    if dev:
        alice_config = AliceConfiguration(dev_mode=True,
                                          network_middleware=general_config.middleware,
                                          domains={TEMPORARY_DOMAIN},
                                          provider_process=eth_node,
                                          provider_uri=provider_uri,
                                          federated_only=True)

    else:
        try:
            alice_config = AliceConfiguration.from_configuration_file(
                dev_mode=False,
                filepath=config_file,
                domains={network} if network else None,
                network_middleware=general_config.middleware,
                rest_port=discovery_port,
                checksum_address=pay_with,
                provider_process=eth_node,
                provider_uri=provider_uri,
                registry_filepath=registry_filepath)
        except FileNotFoundError:
            return actions.handle_missing_configuration_file(character_config_class=AliceConfiguration,
                                                             config_file=config_file)
    return alice_config


def _create_alice(alice_config, general_config, dev, emitter, hw_wallet, teacher_uri, min_stake, load_seednodes=True):
    #
    # Produce Alice
    #
    client_password = None
    if not alice_config.federated_only:
        if (not hw_wallet or not dev) and not general_config.json_ipc:
            client_password = get_client_password(checksum_address=alice_config.checksum_address)
    try:
        ALICE = actions.make_cli_character(character_config=alice_config,
                                           emitter=general_config.emitter,
                                           unlock_keyring=not dev,
                                           teacher_uri=teacher_uri,
                                           min_stake=min_stake,
                                           client_password=client_password,
                                           load_preferred_teachers=load_seednodes,
                                           start_learning_now=load_seednodes)

        return ALICE
    except NucypherKeyring.AuthenticationFailed as e:
        emitter.echo(str(e), color='red', bold=True)
        click.get_current_context().exit(1)
