import click

from nucypher.characters.banners import BOB_BANNER
from nucypher.characters.control.emitters import IPCStdoutEmitter
from nucypher.cli import actions, painting
from nucypher.cli.config import nucypher_click_config
from nucypher.cli.types import NETWORK_PORT, EXISTING_READABLE_FILE
from nucypher.config.characters import BobConfiguration
from nucypher.config.constants import GLOBAL_DOMAIN
from nucypher.crypto.powers import DecryptingPower


@click.command()
@click.argument('action')
@click.option('--teacher-uri', help="An Ursula URI to start learning from (seednode)", type=click.STRING)
@click.option('--quiet', '-Q', help="Disable logging", is_flag=True)
@click.option('--min-stake', help="The minimum stake the teacher must have to be a teacher", type=click.INT, default=0)
@click.option('--discovery-port', help="The host port to run node discovery services on", type=NETWORK_PORT, default=6151)  # TODO
@click.option('--http-port', help="The host port to run Moe HTTP services on", type=NETWORK_PORT, default=11151)  # TODO
@click.option('--federated-only', '-F', help="Connect only to federated nodes", is_flag=True)
@click.option('--network', help="Network Domain Name", type=click.STRING)
@click.option('--config-root', help="Custom configuration directory", type=click.Path())
@click.option('--config-file', help="Path to configuration file", type=EXISTING_READABLE_FILE)
@click.option('--provider-uri', help="Blockchain provider's URI", type=click.STRING)
@click.option('--registry-filepath', help="Custom contract registry filepath", type=EXISTING_READABLE_FILE)
@click.option('--label', help="The label for a policy", type=click.STRING)
@click.option('--dev', '-d', help="Enable development mode", is_flag=True)
@click.option('--force', help="Don't ask for confirmation", is_flag=True)
@click.option('--dry-run', '-x', help="Execute normally without actually starting the node", is_flag=True)
@click.option('--policy-encrypting-key', help="Encrypting Public Key for Policy as hexadecimal string", type=click.STRING)
@click.option('--alice-verifying-key', help="Alice's verifying key as a hexadecimal string", type=click.STRING)
@click.option('--message-kit', help="The message kit unicode string encoded in base64", type=click.STRING)
@nucypher_click_config
def bob(click_config,
        action,
        quiet,
        teacher_uri,
        min_stake,
        http_port,
        discovery_port,
        federated_only,
        network,
        config_root,
        config_file,
        provider_uri,
        registry_filepath,
        dev,
        force,
        dry_run,
        label,
        policy_encrypting_key,
        alice_verifying_key,
        message_kit):
    """
    Start and manage a "Bob" character.
    """

    if not click_config.json_ipc and not click_config.quiet:
        click.secho(BOB_BANNER)

    if action == 'init':
        """Create a brand-new persistent Bob"""

        if dev:
            click_config.emit(message="WARNING: Using temporary storage area", color='yellow')

        if not config_root:                         # Flag
            config_root = click_config.config_file  # Envvar

        new_bob_config = BobConfiguration.generate(password=click_config.get_password(confirm=True),
                                                   config_root=config_root or click_config,
                                                   rest_host="localhost",
                                                   domains={network} if network else None,
                                                   federated_only=federated_only,
                                                   no_registry=click_config.no_registry,
                                                   registry_filepath=registry_filepath,
                                                   provider_uri=provider_uri)

        return painting.paint_new_installation_help(new_configuration=new_bob_config,
                                                    config_file=config_file)

    #
    # Get Bob Configuration
    #

    if dev:
        bob_config = BobConfiguration(dev_mode=True,
                                      domains={network},
                                      provider_uri=provider_uri,
                                      federated_only=True,
                                      network_middleware=click_config.middleware)
    else:

        try:
            bob_config = BobConfiguration.from_configuration_file(
                filepath=config_file,
                domains={network or GLOBAL_DOMAIN},
                rest_port=discovery_port,
                provider_uri=provider_uri,
                network_middleware=click_config.middleware)
        except FileNotFoundError:
            return actions.handle_missing_configuration_file(character_config_class=BobConfiguration,
                                                             config_file=config_file)

    # Teacher Ursula
    teacher_uris = [teacher_uri] if teacher_uri else list()
    teacher_nodes = actions.load_seednodes(teacher_uris=teacher_uris,
                                           min_stake=min_stake,
                                           federated_only=federated_only,
                                           network_middleware=click_config.middleware)

    if not dev:
        click_config.unlock_keyring(character_configuration=bob_config)

    # Produce
    BOB = bob_config(known_nodes=teacher_nodes, network_middleware=click_config.middleware)

    # Switch to character control emitter
    if click_config.json_ipc:
        BOB.controller.emitter = IPCStdoutEmitter(quiet=click_config.quiet)

    if action == "run":
        click_config.emitter(message=f"Bob Verifying Key {bytes(BOB.stamp).hex()}", color='green', bold=True)
        bob_encrypting_key = bytes(BOB.public_keys(DecryptingPower)).hex()
        click_config.emitter(message=f"Bob Encrypting Key {bob_encrypting_key}", color="blue", bold=True)
        controller = BOB.make_web_controller()
        BOB.log.info('Starting HTTP Character Web Controller')
        return controller.start(http_port=http_port, dry_run=dry_run)

    elif action == "view":
        """Paint an existing configuration to the console"""
        response = BobConfiguration._read_configuration_file(filepath=config_file or bob_config.config_file_location)
        return BOB.controller.emitter(response=response)

    elif action == "public-keys":
        response = BOB.controller.public_keys()
        return response

    elif action == "retrieve":

        if not all((label, policy_encrypting_key, alice_verifying_key, message_kit)):
            input_specification, output_specification = BOB.control.get_specifications(interface_name='retrieve')
            required_fields = ', '.join(input_specification)
            raise click.BadArgumentUsage(f'{required_fields} are required flags to retrieve')

        bob_request_data = {
            'label': label,
            'policy_encrypting_key': policy_encrypting_key,
            'alice_verifying_key': alice_verifying_key,
            'message_kit': message_kit,
        }

        response = BOB.controller.retrieve(request=bob_request_data)
        return response

    elif action == "destroy":
        """Delete Bob's character configuration files from the disk"""
        if dev:
            message = "'nucypher ursula destroy' cannot be used in --dev mode"
            raise click.BadOptionUsage(option_name='--dev', message=message)
        return actions.destroy_configuration(character_config=bob_config)

    else:
        raise click.BadArgumentUsage(f"No such argument {action}")
