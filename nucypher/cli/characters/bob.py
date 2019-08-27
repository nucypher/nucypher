import click

from nucypher.blockchain.eth.interfaces import BlockchainInterfaceFactory
from nucypher.characters.banners import BOB_BANNER
from nucypher.cli import actions, painting
from nucypher.cli.actions import get_nucypher_password, select_client_account
from nucypher.cli.config import nucypher_click_config
from nucypher.cli.types import NETWORK_PORT, EXISTING_READABLE_FILE, EIP55_CHECKSUM_ADDRESS
from nucypher.config.characters import BobConfiguration
from nucypher.config.constants import DEFAULT_CONFIG_ROOT
from nucypher.crypto.powers import DecryptingPower


@click.command()
@click.argument('action')
@click.option('--checksum-address', help="Run with a specified account", type=EIP55_CHECKSUM_ADDRESS)
@click.option('--teacher', 'teacher_uri', help="An Ursula URI to start learning from (seednode)", type=click.STRING)
@click.option('--min-stake', help="The minimum stake the teacher must have to be a teacher", type=click.INT, default=0)
@click.option('--discovery-port', help="The host port to run node discovery services on", type=NETWORK_PORT)
@click.option('--controller-port', help="The host port to run Bob HTTP services on", type=NETWORK_PORT, default=BobConfiguration.DEFAULT_CONTROLLER_PORT)
@click.option('--federated-only', '-F', help="Connect only to federated nodes", is_flag=True)
@click.option('--network', help="Network Domain Name", type=click.STRING)
@click.option('--config-root', help="Custom configuration directory", type=click.Path())
@click.option('--config-file', help="Path to configuration file", type=EXISTING_READABLE_FILE)
@click.option('--poa', help="Inject POA middleware", is_flag=True, default=None)
@click.option('--provider', 'provider_uri', help="Blockchain provider's URI", type=click.STRING)
@click.option('--registry-filepath', help="Custom contract registry filepath", type=EXISTING_READABLE_FILE)
@click.option('--label', help="The label for a policy", type=click.STRING)
@click.option('--dev', '-d', help="Enable development mode", is_flag=True)
@click.option('--force', help="Don't ask for confirmation", is_flag=True)
@click.option('--dry-run', '-x', help="Execute normally without actually starting the node", is_flag=True)
@click.option('--policy-encrypting-key', help="Encrypting Public Key for Policy as hexadecimal string", type=click.STRING)
@click.option('--alice-verifying-key', help="Alice's verifying key as a hexadecimal string", type=click.STRING)
@click.option('--message-kit', help="The message kit unicode string encoded in base64", type=click.STRING)
@click.option('--sync/--no-sync', default=True)
@nucypher_click_config
def bob(click_config,
        action,
        teacher_uri,
        min_stake,
        controller_port,
        discovery_port,
        federated_only,
        network,
        config_root,
        config_file,
        checksum_address,
        provider_uri,
        registry_filepath,
        dev,
        force,
        poa,
        dry_run,
        label,
        policy_encrypting_key,
        alice_verifying_key,
        message_kit,
        sync):
    """
    "Bob" management commands.

    \b
    Actions
    -------------------------------------------------
    \b
    init         Create a brand new persistent Bob
    view         View existing Bob's configuration.
    run          Start Bob's controller.
    destroy      Delete existing Bob's configuration.
    public-keys  Obtain Bob's public verification and encryption keys.
    retrieve     Obtain plaintext from encrypted data, if access was granted.

    """

    #
    # Validate
    #

    # Banner
    emitter = click_config.emitter
    emitter.clear()
    emitter.banner(BOB_BANNER)

    #
    # Eager Actions
    #

    if action == 'init':
        """Create a brand-new persistent Bob"""

        if dev:
            raise click.BadArgumentUsage("Cannot create a persistent development character")

        if not config_root:  # Flag
            config_root = click_config.config_file  # Envvar

        if not checksum_address and not federated_only:
            checksum_address = select_client_account(emitter=emitter, provider_uri=provider_uri)

        new_bob_config = BobConfiguration.generate(password=get_nucypher_password(confirm=True),
                                                   config_root=config_root or DEFAULT_CONFIG_ROOT,
                                                   checksum_address=checksum_address,
                                                   domains={network} if network else None,
                                                   federated_only=federated_only,
                                                   registry_filepath=registry_filepath,
                                                   provider_uri=provider_uri)

        return painting.paint_new_installation_help(emitter, new_configuration=new_bob_config)

    #
    # Make Bob
    #

    if dev:
        bob_config = BobConfiguration(dev_mode=True,
                                      domains={network},
                                      provider_uri=provider_uri,
                                      federated_only=True,
                                      checksum_address=checksum_address,
                                      network_middleware=click_config.middleware)
    else:

        try:
            bob_config = BobConfiguration.from_configuration_file(
                filepath=config_file,
                domains={network} if network else None,
                checksum_address=checksum_address,
                rest_port=discovery_port,
                provider_uri=provider_uri,
                registry_filepath=registry_filepath,
                network_middleware=click_config.middleware)
        except FileNotFoundError:
            return actions.handle_missing_configuration_file(character_config_class=BobConfiguration,
                                                             config_file=config_file)

    BOB = actions.make_cli_character(character_config=bob_config,
                                     click_config=click_config,
                                     dev=dev,
                                     teacher_uri=teacher_uri,
                                     min_stake=min_stake)

    #
    # Admin Action
    #

    if action == "run":

        # RPC
        if click_config.json_ipc:
            rpc_controller = BOB.make_rpc_controller()
            _transport = rpc_controller.make_control_transport()
            rpc_controller.start()
            return

        # Echo Public Keys
        emitter.message(f"Bob Verifying Key {bytes(BOB.stamp).hex()}", color='green', bold=True)
        bob_encrypting_key = bytes(BOB.public_keys(DecryptingPower)).hex()
        emitter.message(f"Bob Encrypting Key {bob_encrypting_key}", color="blue", bold=True)

        # Start Controller
        controller = BOB.make_web_controller(crash_on_error=click_config.debug)
        BOB.log.info('Starting HTTP Character Web Controller')
        return controller.start(http_port=controller_port , dry_run=dry_run)

    elif action == "view":
        """Paint an existing configuration to the console"""
        response = BobConfiguration._read_configuration_file(filepath=config_file or bob_config.config_file_location)
        return BOB.controller.emitter.ipc(response, request_id=0, duration=0)  # FIXME: #1216 - what are request_id and duration here?

    elif action == "destroy":
        """Delete Bob's character configuration files from the disk"""

        # Validate
        if dev:
            message = "'nucypher bob destroy' cannot be used in --dev mode"
            raise click.BadOptionUsage(option_name='--dev', message=message)

        # Request
        return actions.destroy_configuration(emitter, character_config=bob_config)

    #
    # Bob API Actions
    #

    elif action == "public-keys":
        response = BOB.controller.public_keys()
        return response

    elif action == "retrieve":

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

    else:
        raise click.BadArgumentUsage(f"No such argument {action}")
