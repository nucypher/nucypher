import click
from constant_sorrow.constants import NO_BLOCKCHAIN_CONNECTION

from nucypher.blockchain.eth.interfaces import BlockchainInterfaceFactory
from nucypher.characters.banners import ALICE_BANNER
from nucypher.cli import actions, painting, types
from nucypher.cli.actions import get_nucypher_password, select_client_account, get_client_password
from nucypher.cli.config import nucypher_click_config
from nucypher.cli.types import NETWORK_PORT, EXISTING_READABLE_FILE, EIP55_CHECKSUM_ADDRESS
from nucypher.config.characters import AliceConfiguration
from nucypher.config.keyring import NucypherKeyring


@click.command()
@click.argument('action')
@click.option('--dev', '-d', help="Enable development mode", is_flag=True)
@click.option('--force', help="Don't ask for confirmation", is_flag=True)
@click.option('--dry-run', '-x', help="Execute normally without actually starting the node", is_flag=True)
@click.option('--teacher', 'teacher_uri', help="An Ursula URI to start learning from (seednode)", type=click.STRING)
@click.option('--min-stake', help="The minimum stake the teacher must have to be a teacher", type=click.INT, default=0)
@click.option('--discovery-port', help="The host port to run node discovery services on", type=NETWORK_PORT)
@click.option('--controller-port', help="The host port to run Alice HTTP services on", type=NETWORK_PORT, default=AliceConfiguration.DEFAULT_CONTROLLER_PORT)
@click.option('--federated-only', '-F', help="Connect only to federated nodes", is_flag=True)
@click.option('--network', help="Network Domain Name", type=click.STRING)
@click.option('--config-root', help="Custom configuration directory", type=click.Path())
@click.option('--config-file', help="Path to configuration file", type=EXISTING_READABLE_FILE)
@click.option('--provider', 'provider_uri', help="Blockchain provider's URI", type=click.STRING)
@click.option('--sync/--no-sync', default=True)
@click.option('--hw-wallet/--no-hw-wallet', default=False)
@click.option('--geth', '-G', help="Run using the built-in geth node", is_flag=True)
@click.option('--poa', help="Inject POA middleware", is_flag=True, default=None)
@click.option('--registry-filepath', help="Custom contract registry filepath", type=EXISTING_READABLE_FILE)
@click.option('--pay-with', help="Run with a specified account", type=EIP55_CHECKSUM_ADDRESS)
@click.option('--bob-encrypting-key', help="Bob's encrypting key as a hexadecimal string", type=click.STRING)
@click.option('--bob-verifying-key', help="Bob's verifying key as a hexadecimal string", type=click.STRING)
@click.option('--label', help="The label for a policy", type=click.STRING)
@click.option('--m', help="M-Threshold KFrags", type=click.INT)
@click.option('--n', help="N-Total KFrags", type=click.INT)
@click.option('--value', help="Total policy value (in Wei)", type=types.WEI)
@click.option('--rate', help="Policy rate per period in wei", type=click.FLOAT)
@click.option('--duration-periods', help="Policy duration in periods", type=click.FLOAT)
@click.option('--expiration', help="Expiration Datetime of a policy", type=click.STRING)  # TODO: click.DateTime()
@click.option('--message-kit', help="The message kit unicode string encoded in base64", type=click.STRING)
@nucypher_click_config
def alice(click_config,
          action,

          # Mode
          dev,
          force,
          dry_run,

          # Network
          teacher_uri,
          min_stake,
          federated_only,
          network,
          discovery_port,
          controller_port,

          # Filesystem
          config_root,
          config_file,

          # Blockchain
          pay_with,
          provider_uri,
          geth,
          sync,
          poa,
          registry_filepath,
          hw_wallet,

          # Alice
          bob_encrypting_key,
          bob_verifying_key,
          label,
          m,
          n,
          value,
          rate,
          duration_periods,
          expiration,
          message_kit,

          ):
    """
    "Alice the Policy Authority" management commands.

    \b
    Actions
    -------------------------------------------------
    \b
    init                  Create a brand new persistent Alice
    view                  View existing Alice's configuration.
    run                   Start Alice's controller.
    destroy               Delete existing Alice's configuration.
    public-keys           Obtain Alice's public verification and encryption keys.
    derive-policy-pubkey  Get a policy public key from a policy label.
    grant                 Create and enact an access policy for some Bob.
    revoke                Revoke a policy.
    decrypt               Decrypt data encrypted under an Alice's policy public key.

    """

    #
    # Validate
    #

    if federated_only and geth:
        raise click.BadOptionUsage(option_name="--geth", message="Federated only cannot be used with the --geth flag")

    # Banner
    emitter = click_config.emitter
    emitter.clear()
    emitter.banner(ALICE_BANNER)

    #
    # Managed Ethereum Client
    #

    ETH_NODE = NO_BLOCKCHAIN_CONNECTION
    if geth:
        ETH_NODE = actions.get_provider_process()
        provider_uri = ETH_NODE.provider_uri(scheme='file')

    #
    # Eager Actions (No Authentication Required)
    #

    if action == 'init':
        """Create a brand-new persistent Alice"""

        if dev:
            raise click.BadArgumentUsage("Cannot create a persistent development character")

        if not provider_uri and not federated_only:
            raise click.BadOptionUsage(option_name='--provider',
                                       message="--provider is required to create a new decentralized alice.")

        if not config_root:                         # Flag
            config_root = click_config.config_file  # Envvar

        if not pay_with and not federated_only:
            pay_with = select_client_account(emitter=emitter, provider_uri=provider_uri)

        new_alice_config = AliceConfiguration.generate(password=get_nucypher_password(confirm=True),
                                                       config_root=config_root,
                                                       checksum_address=pay_with,
                                                       domains={network} if network else None,
                                                       federated_only=federated_only,
                                                       registry_filepath=registry_filepath,
                                                       provider_process=ETH_NODE,
                                                       poa=poa,
                                                       provider_uri=provider_uri,
                                                       m=m,
                                                       n=n,
                                                       duration_periods=duration_periods,
                                                       rate=rate)

        painting.paint_new_installation_help(emitter, new_configuration=new_alice_config)
        return  # Exit

    elif action == "view":
        """Paint an existing configuration to the console"""
        configuration_file_location = config_file or AliceConfiguration.default_filepath()
        response = AliceConfiguration._read_configuration_file(filepath=configuration_file_location)
        return emitter.ipc(response=response, request_id=0, duration=0)  # FIXME: what are request_id and duration here?

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
                dev_mode=False,
                filepath=config_file,
                domains={network} if network else None,
                network_middleware=click_config.middleware,
                rest_port=discovery_port,
                checksum_address=pay_with,
                provider_process=ETH_NODE,
                provider_uri=provider_uri,
                registry_filepath=registry_filepath)
        except FileNotFoundError:
            return actions.handle_missing_configuration_file(character_config_class=AliceConfiguration,
                                                             config_file=config_file)

    if action == "destroy":
        """Delete all configuration files from the disk"""
        if dev:
            message = "'nucypher alice destroy' cannot be used in --dev mode"
            raise click.BadOptionUsage(option_name='--dev', message=message)
        return actions.destroy_configuration(emitter, character_config=alice_config, force=force)

    #
    # Produce Alice
    #

    # TODO: OH MY.
    client_password = None
    if not alice_config.federated_only:
        if (not hw_wallet or not dev) and not click_config.json_ipc:
            client_password = get_client_password(checksum_address=alice_config.checksum_address)

    try:
        ALICE = actions.make_cli_character(character_config=alice_config,
                                           click_config=click_config,
                                           dev=dev,
                                           teacher_uri=teacher_uri,
                                           min_stake=min_stake,
                                           client_password=client_password)
    except NucypherKeyring.AuthenticationFailed as e:
        emitter.echo(str(e), color='red', bold=True)
        click.get_current_context().exit(1)
        # TODO: Exit codes (not only for this, but for other exceptions)

    #
    # Admin Actions
    #

    if action == "run":
        """Start Alice Controller"""

        try:

            # RPC
            if click_config.json_ipc:
                rpc_controller = ALICE.make_rpc_controller()
                _transport = rpc_controller.make_control_transport()
                rpc_controller.start()
                return

            # HTTP
            else:
                emitter.message(f"Alice Verifying Key {bytes(ALICE.stamp).hex()}", color="green", bold=True)
                controller = ALICE.make_web_controller(crash_on_error=click_config.debug)
                ALICE.log.info('Starting HTTP Character Web Controller')
                emitter.message(f'Running HTTP Alice Controller at http://localhost:{controller_port}')
                return controller.start(http_port=controller_port, dry_run=dry_run)

        # Handle Crash
        except Exception as e:
            alice_config.log.critical(str(e))
            emitter.message(f"{e.__class__.__name__} {e}", color='red', bold=True)
            if click_config.debug:
                raise  # Crash :-(
            return

    #
    # Alice API
    #

    elif action == "public-keys":
        response = ALICE.controller.public_keys()
        return response

    elif action == "derive-policy-pubkey":

        # Validate
        if not label:
            raise click.BadOptionUsage(option_name='label',
                                       message="--label is required for deriving a policy encrypting key.")

        # Request
        return ALICE.controller.derive_policy_encrypting_key(label=label)

    elif action == "grant":

        # Validate
        if not all((bob_verifying_key, bob_encrypting_key, label)):
            raise click.BadArgumentUsage(message="--bob-verifying-key, --bob-encrypting-key, and --label are "
                                                 "required options to grant (optionally --m, --n, and --expiration).")

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

    elif action == "revoke":

        # Validate
        if not label and bob_verifying_key:
            raise click.BadArgumentUsage(message=f"--label and --bob-verifying-key are required options for revoke.")

        # Request
        revoke_request = {'label': label, 'bob_verifying_key': bob_verifying_key}
        return ALICE.controller.revoke(request=revoke_request)

    elif action == "decrypt":

        # Validate
        if not all((label, message_kit)):
            input_specification, output_specification = ALICE.controller.get_specifications(interface_name=action)
            required_fields = ', '.join(input_specification)
            raise click.BadArgumentUsage(f'{required_fields} are required flags to decrypt')

        # Request
        request_data = {'label': label, 'message_kit': message_kit}
        response = ALICE.controller.decrypt(request=request_data)
        return response

    else:
        raise click.BadArgumentUsage(f"No such argument {action}")
