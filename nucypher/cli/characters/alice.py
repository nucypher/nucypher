import datetime
from base64 import b64encode

import click
import maya

from nucypher.characters.banners import ALICE_BANNER
from nucypher.characters.control.emitters import IPCStdoutEmitter
from nucypher.cli import actions, painting
from nucypher.cli.config import nucypher_click_config
from nucypher.cli.types import NETWORK_PORT, EXISTING_READABLE_FILE, EIP55_CHECKSUM_ADDRESS
from nucypher.config.characters import AliceConfiguration
from nucypher.config.constants import GLOBAL_DOMAIN


@click.command()
@click.argument('action')
@click.option('--checksum-address', help="Run with a specified account", type=EIP55_CHECKSUM_ADDRESS)
@click.option('--teacher-uri', help="An Ursula URI to start learning from (seednode)", type=click.STRING)
@click.option('--min-stake', help="The minimum stake the teacher must have to be a teacher", type=click.INT, default=0)
@click.option('--discovery-port', help="The host port to run node discovery services on", type=NETWORK_PORT, default=9151)  # TODO
@click.option('--http-port', help="The host port to run Moe HTTP services on", type=NETWORK_PORT, default=8151)  # TODO
@click.option('--federated-only', '-F', help="Connect only to federated nodes", is_flag=True)
@click.option('--network', help="Network Domain Name", type=click.STRING)
@click.option('--config-root', help="Custom configuration directory", type=click.Path())
@click.option('--config-file', help="Path to configuration file", type=EXISTING_READABLE_FILE)
@click.option('--provider-uri', help="Blockchain provider's URI", type=click.STRING)
@click.option('--no-registry', help="Skip importing the default contract registry", is_flag=True)
@click.option('--registry-filepath', help="Custom contract registry filepath", type=EXISTING_READABLE_FILE)
@click.option('--bob-encrypting-key', help="Bob's encrypting key as a hexideicmal string", type=click.STRING)
@click.option('--bob-verifying-key', help="Bob's verifying key as a hexideicmal string", type=click.STRING)
@click.option('--label', help="The label for a policy", type=click.STRING)
@click.option('--m', help="M-Threshold KFrags", type=click.INT)
@click.option('--n', help="N-Total KFrags", type=click.INT)
@click.option('--dev', '-d', help="Enable development mode", is_flag=True)
@click.option('--force', help="Don't ask for confirmation", is_flag=True)
@click.option('--dry-run', '-x', help="Execute normally without actually starting the node", is_flag=True)
@nucypher_click_config
def alice(click_config,
          action,
          checksum_address,
          teacher_uri,
          min_stake,
          http_port,
          discovery_port,
          federated_only,
          network,
          config_root,
          config_file,
          provider_uri,
          no_registry,
          registry_filepath,
          dev,
          force,
          dry_run,
          bob_encrypting_key,
          bob_verifying_key,
          label,
          m,
          n):

    """
    Start and manage an "Alice" character.
    """

    if not click_config.json_ipc and not click_config.quiet:
        click.secho(ALICE_BANNER)

    if action == 'init':
        """Create a brand-new persistent Alice"""

        if not network:
            raise click.BadArgumentUsage('--network is required to initialize a new configuration.')

        if dev:
            click_config.emitter(message="WARNING: Using temporary storage area", color='yellow')

        if not config_root:                         # Flag
            config_root = click_config.config_file  # Envvar

        new_alice_config = AliceConfiguration.generate(password=click_config.get_password(confirm=True),
                                                       config_root=config_root,
                                                       checksum_public_address=checksum_address,
                                                       rest_host="localhost",
                                                       domains={network} if network else None,
                                                       federated_only=federated_only,
                                                       no_registry=no_registry,
                                                       registry_filepath=registry_filepath,
                                                       provider_uri=provider_uri)

        return painting.paint_new_installation_help(new_configuration=new_alice_config,
                                                    config_root=config_root,
                                                    config_file=config_file)
    #
    # Get Alice Configuration
    #

    if dev:
        alice_config = AliceConfiguration(dev_mode=True,
                                          network_middleware=click_config.middleware,
                                          domains={network},
                                          provider_uri=provider_uri,
                                          federated_only=True)

    else:
        try:
            alice_config = AliceConfiguration.from_configuration_file(
                filepath=config_file,
                domains={network or GLOBAL_DOMAIN},
                network_middleware=click_config.middleware,
                rest_port=discovery_port,
                checksum_public_address=checksum_address,
                provider_uri=provider_uri)
        except FileNotFoundError:
            return actions.handle_missing_configuration_file(character_config_class=AliceConfiguration,
                                                             config_file=config_file)

    if not dev:
        click_config.unlock_keyring(character_configuration=alice_config)

    # Teacher Ursula
    teacher_uris = [teacher_uri] if teacher_uri else list()
    teacher_nodes = actions.load_seednodes(teacher_uris=teacher_uris,
                                           min_stake=min_stake,
                                           federated_only=federated_only,
                                           network_middleware=click_config.middleware)
    # Produce
    ALICE = alice_config(known_nodes=teacher_nodes, network_middleware=click_config.middleware)

    # Switch to character control emitter
    if click_config.json_ipc:
        ALICE.controller.emitter = IPCStdoutEmitter(quiet=click_config.quiet)

    if action == "run":
        """Start Alice Web Controller"""
        ALICE.controller.emitter(message=f"Alice Verifying Key {bytes(ALICE.stamp).hex()}", color="green", bold=True)
        controller = ALICE.make_web_controller(crash_on_error=click_config.debug)
        ALICE.log.info('Starting HTTP Character Web Controller')
        return controller.start(http_port=http_port, dry_run=dry_run)

    elif action == "view":
        """Paint an existing configuration to the console"""
        configuration_file_location = config_file or alice_config.config_file_location
        response = AliceConfiguration._read_configuration_file(filepath=configuration_file_location)
        return ALICE.controller.emitter(response=response)         # TODO: Uses character control instead

    elif action == "public-keys":
        response = ALICE.controller.public_keys()
        return response

    elif action == "create-policy":
        if not all((bob_verifying_key, bob_encrypting_key, label)):
            raise click.BadArgumentUsage(message="--bob-verifying-key, --bob-encrypting-key, and --label are "
                                                 "required options to create a new policy.")

        create_policy_request = {
            'bob_encrypting_key': bob_encrypting_key,
            'bob_verifying_key': bob_verifying_key,
            'label': label,
            'm': m,
            'n': n,
        }

        return ALICE.controller.create_policy(request=create_policy_request)

    elif action == "derive-policy-pubkey":
        return ALICE.controller.derive_policy_encrypting_key(label=label)

    elif action == "grant":
        grant_request = {
            'bob_encrypting_key': bob_encrypting_key,
            'bob_verifying_key': bob_verifying_key,
            'label': label,
            'm': m,
            'n': n,
            'expiration': (maya.now() + datetime.timedelta(days=3)).iso8601(),  # TODO
        }

        return ALICE.controller.grant(request=grant_request)

    elif action == "revoke":
        revoke_request = {
            'label': label,
            'bob_verifying_key': bob_verifying_key
        }
        return ALICE.controller.revoke(request=revoke_request)

    elif action == "destroy":
        """Delete all configuration files from the disk"""
        if dev:
            message = "'nucypher ursula destroy' cannot be used in --dev mode"
            raise click.BadOptionUsage(option_name='--dev', message=message)
        return actions.destroy_configuration(character_config=alice_config, force=force)

    else:
        raise click.BadArgumentUsage(f"No such argument {action}")
