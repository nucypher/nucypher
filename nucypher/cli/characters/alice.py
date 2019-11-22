import functools

import click
from constant_sorrow.constants import NO_BLOCKCHAIN_CONNECTION

from nucypher.characters.banners import ALICE_BANNER
from nucypher.cli import actions, painting, types
from nucypher.cli.actions import get_nucypher_password, select_client_account, get_client_password
from nucypher.cli.config import nucypher_click_config
from nucypher.cli.types import NETWORK_PORT, EXISTING_READABLE_FILE, EIP55_CHECKSUM_ADDRESS
from nucypher.config.characters import AliceConfiguration
from nucypher.config.keyring import NucypherKeyring


# Args (geth, provider_uri, federated_only, dev, pay_with, network, registry_filepath)
def _admin_options(func):
    @click.option('--geth', '-G', help="Run using the built-in geth node", is_flag=True)
    @click.option('--provider', 'provider_uri', help="Blockchain provider's URI", type=click.STRING)
    @click.option('--federated-only', '-F', help="Connect only to federated nodes", is_flag=True)
    @click.option('--dev', '-d', help="Enable development mode", is_flag=True)
    @click.option('--pay-with', help="Run with a specified account", type=EIP55_CHECKSUM_ADDRESS)
    @click.option('--network', help="Network Domain Name", type=click.STRING)
    @click.option('--registry-filepath', help="Custom contract registry filepath", type=EXISTING_READABLE_FILE)
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        return func(*args, **kwargs)
    return wrapper


# Args (geth, provider_uri, federated_only, dev, pay_with, network, registry_filepath, config_file, discovery_port,
#       hw_wallet, teacher_uri, min_stake)
def _api_options(func):
    @_admin_options
    @click.option('--config-file', help="Path to configuration file", type=EXISTING_READABLE_FILE)
    @click.option('--discovery-port', help="The host port to run node discovery services on", type=NETWORK_PORT)
    @click.option('--hw-wallet/--no-hw-wallet', default=False)
    @click.option('--teacher', 'teacher_uri', help="An Ursula URI to start learning from (seednode)", type=click.STRING)
    @click.option('--min-stake', help="The minimum stake the teacher must have to be a teacher", type=click.INT,
                  default=0)
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        return func(*args, **kwargs)
    return wrapper


@click.group()
def alice():
    """
    "Alice the Policy Authority" management commands.
    """
    pass


@alice.command()
@_admin_options
@click.option('--config-root', help="Custom configuration directory", type=click.Path())
@click.option('--poa', help="Inject POA middleware", is_flag=True, default=None)
@click.option('--light', help="Indicate that node is light", is_flag=True, default=False)
@click.option('--m', help="M-Threshold KFrags", type=click.INT)
@click.option('--n', help="N-Total KFrags", type=click.INT)
@click.option('--rate', help="Policy rate per period in wei", type=click.FLOAT)
@click.option('--duration-periods', help="Policy duration in periods", type=click.FLOAT)
@nucypher_click_config
def init(click_config,

         # Admin Options
         geth,
         provider_uri,
         federated_only,
         dev,
         pay_with,
         network,
         registry_filepath,

         # Other
         config_root, poa, light, m, n, rate, duration_periods):
    """
    Create a brand new persistent Alice.
    """

    ### Setup ###
    emitter = _setup_emitter(click_config)

    if federated_only and geth:
        raise click.BadOptionUsage(option_name="--geth", message="Federated only cannot be used with the --geth flag")

    #
    # Managed Ethereum Client
    #

    ETH_NODE = NO_BLOCKCHAIN_CONNECTION
    if geth:
        ETH_NODE = actions.get_provider_process()
        provider_uri = ETH_NODE.provider_uri(scheme='file')

    #############

    if dev:
        raise click.BadArgumentUsage("Cannot create a persistent development character")

    if not provider_uri and not federated_only:
        raise click.BadOptionUsage(option_name='--provider',
                                   message="--provider is required to create a new decentralized alice.")

    if not config_root:  # Flag
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
                                                   light=light,
                                                   provider_uri=provider_uri,
                                                   m=m,
                                                   n=n,
                                                   duration_periods=duration_periods,
                                                   rate=rate)

    painting.paint_new_installation_help(emitter, new_configuration=new_alice_config)


@alice.command()
@click.option('--config-file', help="Path to configuration file", type=EXISTING_READABLE_FILE)
@nucypher_click_config
def view(click_config, config_file):
    """
    View existing Alice's configuration.
    """
    emitter = _setup_emitter(click_config)

    configuration_file_location = config_file or AliceConfiguration.default_filepath()
    response = AliceConfiguration._read_configuration_file(filepath=configuration_file_location)
    return emitter.ipc(response=response, request_id=0, duration=0)  # FIXME: what are request_id and duration here?


@alice.command()
@_admin_options
@click.option('--config-file', help="Path to configuration file", type=EXISTING_READABLE_FILE)
@click.option('--discovery-port', help="The host port to run node discovery services on", type=NETWORK_PORT)
@click.option('--force', help="Don't ask for confirmation", is_flag=True)
@nucypher_click_config
def destroy(click_config,

            # Admin Options
            geth, provider_uri, federated_only, dev, pay_with, network, registry_filepath,

            # Other
            config_file, discovery_port, force):
    """
    Delete existing Alice's configuration.
    """
    ### Setup ###
    emitter = _setup_emitter(click_config)

    alice_config, provider_uri = _get_alice_config(click_config, config_file, dev, discovery_port, federated_only,
                                                   geth, network, pay_with, provider_uri, registry_filepath)
    #############

    if dev:
        message = "'nucypher alice destroy' cannot be used in --dev mode"
        raise click.BadOptionUsage(option_name='--dev', message=message)
    return actions.destroy_configuration(emitter, character_config=alice_config, force=force)


@alice.command()
@_api_options
@click.option('--controller-port', help="The host port to run Alice HTTP services on", type=NETWORK_PORT,
              default=AliceConfiguration.DEFAULT_CONTROLLER_PORT)
@click.option('--dry-run', '-x', help="Execute normally without actually starting the node", is_flag=True)
@nucypher_click_config
def run(click_config,

        # API Options
        geth, provider_uri, federated_only, dev, pay_with, network, registry_filepath,
        config_file, discovery_port, hw_wallet, teacher_uri, min_stake,

        # Other
        controller_port, dry_run):
    """
    Start Alice's controller.
    """

    ### Setup ###
    emitter = _setup_emitter(click_config)

    alice_config, provider_uri = _get_alice_config(click_config, config_file, dev, discovery_port, federated_only,
                                                   geth, network, pay_with, provider_uri, registry_filepath)
    #############

    ALICE = _create_alice(alice_config, click_config, dev, emitter, hw_wallet, teacher_uri, min_stake)

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


@alice.command("public-keys")
@_api_options
@nucypher_click_config
def public_keys(click_config,

                # API Options
                geth, provider_uri, federated_only, dev, pay_with, network, registry_filepath,
                config_file, discovery_port, hw_wallet, teacher_uri, min_stake):
    """
    Obtain Alice's public verification and encryption keys.
    """

    ### Setup ###
    emitter = _setup_emitter(click_config)
    alice_config, provider_uri = _get_alice_config(click_config, config_file, dev, discovery_port, federated_only,
                                                   geth, network, pay_with, provider_uri, registry_filepath)
    #############

    ALICE = _create_alice(alice_config, click_config, dev, emitter, hw_wallet, teacher_uri, min_stake)

    response = ALICE.controller.public_keys()
    return response


@alice.command('derive-policy-pubkey')
@click.option('--label', help="The label for a policy", type=click.STRING, required=True)
@_api_options
@nucypher_click_config
def derive_policy_pubkey(click_config,

                         # Other (required)
                         label,

                         # API Options
                         geth, provider_uri, federated_only, dev, pay_with, network, registry_filepath,
                         config_file, discovery_port, hw_wallet, teacher_uri, min_stake):
    """
    Get a policy public key from a policy label.
    """
    ### Setup ###
    emitter = _setup_emitter(click_config)

    alice_config, provider_uri = _get_alice_config(click_config, config_file, dev, discovery_port, federated_only,
                                                   geth, network, pay_with, provider_uri, registry_filepath)
    #############

    ALICE = _create_alice(alice_config, click_config, dev, emitter, hw_wallet, teacher_uri, min_stake)

    # Request
    return ALICE.controller.derive_policy_encrypting_key(label=label)


@alice.command()
@click.option('--bob-encrypting-key', help="Bob's encrypting key as a hexadecimal string", type=click.STRING,
              required=True)
@click.option('--bob-verifying-key', help="Bob's verifying key as a hexadecimal string", type=click.STRING,
              required=True)
@click.option('--label', help="The label for a policy", type=click.STRING, required=True)
@click.option('--m', help="M-Threshold KFrags", type=click.INT)
@click.option('--n', help="N-Total KFrags", type=click.INT)
@click.option('--expiration', help="Expiration Datetime of a policy", type=click.STRING)  # TODO: click.DateTime()
@click.option('--value', help="Total policy value (in Wei)", type=types.WEI)
@_api_options
@nucypher_click_config
def grant(click_config,
          # Other (required)
          bob_encrypting_key, bob_verifying_key, label,

          # Other
          m, n, expiration, value,

          # API Options
          geth, provider_uri, federated_only, dev, pay_with, network, registry_filepath,
          config_file, discovery_port, hw_wallet, teacher_uri, min_stake):
    """
    Create and enact an access policy for some Bob.
    """
    ### Setup ###
    emitter = _setup_emitter(click_config)

    alice_config, provider_uri = _get_alice_config(click_config, config_file, dev, discovery_port, federated_only,
                                                   geth, network, pay_with, provider_uri, registry_filepath)
    #############

    ALICE = _create_alice(alice_config, click_config, dev, emitter, hw_wallet, teacher_uri, min_stake)

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
@click.option('--bob-verifying-key', help="Bob's verifying key as a hexadecimal string", type=click.STRING,
              required=True)
@click.option('--label', help="The label for a policy", type=click.STRING, required=True)
@_api_options
@nucypher_click_config
def revoke(click_config,

           # Other (required)
           bob_verifying_key, label,

           # API Options
           geth, provider_uri, federated_only, dev, pay_with, network, registry_filepath,
           config_file, discovery_port, hw_wallet, teacher_uri, min_stake):
    """
    Revoke a policy.
    """
    ### Setup ###
    emitter = _setup_emitter(click_config)

    alice_config, provider_uri = _get_alice_config(click_config, config_file, dev, discovery_port, federated_only,
                                                   geth, network, pay_with, provider_uri, registry_filepath)
    #############

    ALICE = _create_alice(alice_config, click_config, dev, emitter, hw_wallet, teacher_uri, min_stake)

    # Request
    revoke_request = {'label': label, 'bob_verifying_key': bob_verifying_key}
    return ALICE.controller.revoke(request=revoke_request)


@alice.command()
@click.option('--label', help="The label for a policy", type=click.STRING, required=True)
@click.option('--message-kit', help="The message kit unicode string encoded in base64", type=click.STRING,
              required=True)
@_api_options
@nucypher_click_config
def decrypt(click_config,

            # Other (required)
            label, message_kit,

            # API Options
            geth, provider_uri, federated_only, dev, pay_with, network, registry_filepath,
            config_file, discovery_port, hw_wallet, teacher_uri, min_stake):
    """
    Decrypt data encrypted under an Alice's policy public key.
    """
    ### Setup ###
    emitter = _setup_emitter(click_config)

    alice_config, provider_uri = _get_alice_config(click_config, config_file, dev, discovery_port, federated_only,
                                                   geth, network, pay_with, provider_uri, registry_filepath)
    #############

    ALICE = _create_alice(alice_config, click_config, dev, emitter, hw_wallet, teacher_uri, min_stake)

    # Request
    request_data = {'label': label, 'message_kit': message_kit}
    response = ALICE.controller.decrypt(request=request_data)
    return response


def _setup_emitter(click_config):
    # Banner
    emitter = click_config.emitter
    emitter.clear()
    emitter.banner(ALICE_BANNER)

    return emitter


def _get_alice_config(click_config, config_file, dev, discovery_port, federated_only, geth, network, pay_with,
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
    alice_config = _get_or_create_alice_config(click_config, dev, network, ETH_NODE, provider_uri,
                                               config_file, discovery_port, pay_with, registry_filepath)
    return alice_config, provider_uri


def _get_or_create_alice_config(click_config, dev, network, eth_node, provider_uri, config_file,
                                discovery_port, pay_with, registry_filepath):
    if dev:
        alice_config = AliceConfiguration(dev_mode=True,
                                          network_middleware=click_config.middleware,
                                          domains={network},
                                          provider_process=eth_node,
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
                provider_process=eth_node,
                provider_uri=provider_uri,
                registry_filepath=registry_filepath)
        except FileNotFoundError:
            return actions.handle_missing_configuration_file(character_config_class=AliceConfiguration,
                                                             config_file=config_file)
    return alice_config


def _create_alice(alice_config, click_config, dev, emitter, hw_wallet, teacher_uri, min_stake):
    #
    # Produce Alice
    #
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

        return ALICE
    except NucypherKeyring.AuthenticationFailed as e:
        emitter.echo(str(e), color='red', bold=True)
        click.get_current_context().exit(1)
