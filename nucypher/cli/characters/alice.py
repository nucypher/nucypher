import datetime
import json

import click
import maya
from constant_sorrow.constants import NO_BLOCKCHAIN_CONNECTION

from nucypher.characters.banners import ALICE_BANNER
from nucypher.characters.control.emitters import IPCStdoutEmitter
from nucypher.cli import actions, painting
from nucypher.cli.config import nucypher_click_config
from nucypher.cli.types import NETWORK_PORT, EXISTING_READABLE_FILE, EIP55_CHECKSUM_ADDRESS
from nucypher.config.characters import AliceConfiguration


@click.command()
@click.argument('action')
@click.option('--pay-with', help="Run with a specified account", type=EIP55_CHECKSUM_ADDRESS)
@click.option('--teacher-uri', help="An Ursula URI to start learning from (seednode)", type=click.STRING)
@click.option('--min-stake', help="The minimum stake the teacher must have to be a teacher", type=click.INT, default=0)
@click.option('--discovery-port', help="The host port to run node discovery services on", type=NETWORK_PORT, default=9151)  # TODO
@click.option('--http-port', help="The host port to run Moe HTTP services on", type=NETWORK_PORT, default=8151)  # TODO
@click.option('--federated-only', '-F', help="Connect only to federated nodes", is_flag=True)
@click.option('--network', help="Network Domain Name", type=click.STRING)
@click.option('--config-root', help="Custom configuration directory", type=click.Path())
@click.option('--config-file', help="Path to configuration file", type=EXISTING_READABLE_FILE)
@click.option('--provider-uri', help="Blockchain provider's URI", type=click.STRING)
@click.option('--geth', '-G', help="Run using the built-in geth node", is_flag=True)
@click.option('--poa', help="Inject POA middleware", is_flag=True, default=None)
@click.option('--no-registry', help="Skip importing the default contract registry", is_flag=True)
@click.option('--registry-filepath', help="Custom contract registry filepath", type=EXISTING_READABLE_FILE)
@click.option('--bob-encrypting-key', help="Bob's encrypting key as a hexadeicmal string", type=click.STRING)
@click.option('--bob-verifying-key', help="Bob's verifying key as a hexadeicmal string", type=click.STRING)
@click.option('--label', help="The label for a policy", type=click.STRING)
@click.option('--m', help="M-Threshold KFrags", type=click.INT)
@click.option('--n', help="N-Total KFrags", type=click.INT)
@click.option('--value', help="M-Threshold KFrags", type=click.FLOAT)
@click.option('--dev', '-d', help="Enable development mode", is_flag=True)
@click.option('--force', help="Don't ask for confirmation", is_flag=True)
@click.option('--dry-run', '-x', help="Execute normally without actually starting the node", is_flag=True)
@click.option('--message-kit', help="The message kit unicode string encoded in base64", type=click.STRING)
@nucypher_click_config
def alice(click_config,
          action,
          pay_with,
          teacher_uri,
          min_stake,
          http_port,
          discovery_port,
          federated_only,
          network,
          config_root,
          config_file,
          provider_uri,
          geth,
          poa,
          no_registry,
          registry_filepath,
          dev,
          force,
          dry_run,
          bob_encrypting_key,
          bob_verifying_key,
          label,
          m,
          n,
          value,
          message_kit):

    """
    Start and manage an "Alice" character.
    """
    # Validate
    if federated_only and geth:
        raise click.BadOptionUsage(option_name="--geth", message="Federated only cannot be used with the --geth flag")

    if not click_config.json_ipc and not click_config.quiet:
        click.secho(ALICE_BANNER)

    ETH_NODE = NO_BLOCKCHAIN_CONNECTION
    if geth:
        ETH_NODE = actions.get_provider_process()
        provider_uri = ETH_NODE.provider_uri(scheme='file')

    if action == 'init':
        """Create a brand-new persistent Alice"""

        if dev:
            raise click.BadArgumentUsage("Cannot create a persistent development character")

        if not config_root:                         # Flag
            config_root = click_config.config_file  # Envvar

        new_alice_config = AliceConfiguration.generate(password=click_config.get_password(confirm=True),
                                                       config_root=config_root,
                                                       checksum_address=pay_with,
                                                       rest_host="localhost",
                                                       domains={network} if network else None,
                                                       federated_only=federated_only,
                                                       download_registry=no_registry,
                                                       registry_filepath=registry_filepath,
                                                       provider_process=ETH_NODE,
                                                       provider_uri=provider_uri)

        return painting.paint_new_installation_help(new_configuration=new_alice_config,
                                                    config_root=config_root,
                                                    config_file=config_file)

    elif action == "view":
        """Paint an existing configuration to the console"""
        configuration_file_location = config_file or AliceConfiguration.DEFAULT_CONFIG_FILE_LOCATION
        response = AliceConfiguration._read_configuration_file(filepath=configuration_file_location)
        for k, v in response.items():
            click.secho(f'{k} .... {v}')
        return

    #
    # Get Alice Configuration
    #

    if dev:
        alice_config = AliceConfiguration(dev_mode=True,
                                          network_middleware=click_config.middleware,
                                          domains={network},
                                          provider_process=ETH_NODE,
                                          provider_uri=provider_uri,
                                          federated_only=True)

    else:
        try:
            alice_config = AliceConfiguration.from_configuration_file(
                filepath=config_file,
                domains={network} if network else None,
                network_middleware=click_config.middleware,
                rest_port=discovery_port,
                checksum_address=pay_with,
                provider_process=ETH_NODE,
                provider_uri=provider_uri)
        except FileNotFoundError:
            return actions.handle_missing_configuration_file(character_config_class=AliceConfiguration,
                                                             config_file=config_file)

    if not alice_config.federated_only:
        click_config.connect_to_blockchain(character_configuration=alice_config)
    if not dev:
        click_config.unlock_keyring(character_configuration=alice_config,
                                    password=click_config.get_password(confirm=False))

    # Teacher Ursula
    teacher_nodes = actions.load_seednodes(teacher_uris=[teacher_uri] if teacher_uri else None,
                                           min_stake=min_stake,
                                           federated_only=alice_config.federated_only,
                                           network_domains=alice_config.domains,
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
        if not label:
            raise click.BadOptionUsage(option_name='label',
                                       message="--label is required for deriving a policy encrypting key.")
        return ALICE.controller.derive_policy_encrypting_key(label=label)

    elif action == "grant":
        grant_request = {
            'bob_encrypting_key': bob_encrypting_key,
            'bob_verifying_key': bob_verifying_key,
            'label': label,
            'm': m,
            'n': n,
            'expiration': (maya.now() + datetime.timedelta(days=3)).iso8601(),
        }

        if not ALICE.federated_only:
            grant_request.update({'value': value})

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

    elif action == "decrypt":

        if not all((label, message_kit)):
            input_specification, output_specification = ALICE.controller.get_specifications(interface_name='decrypt')
            required_fields = ', '.join(input_specification)
            raise click.BadArgumentUsage(f'{required_fields} are required flags to decrypt')

        request_data = {
            'label': label,
            'message_kit': message_kit,
        }
        response = ALICE.controller.decrypt(request=request_data)
        return response

    else:
        raise click.BadArgumentUsage(f"No such argument {action}")
