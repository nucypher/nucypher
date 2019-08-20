import click
from umbral.keys import UmbralPublicKey

from nucypher.characters.banners import ENRICO_BANNER
from nucypher.characters.lawful import Enrico
from nucypher.cli.config import nucypher_click_config
from nucypher.cli.types import NETWORK_PORT


@click.command()
@click.argument('action')
@click.option('--dry-run', '-x', help="Execute normally without actually starting the node", is_flag=True)
@click.option('--http-port', help="The host port to run Moe HTTP services on", type=NETWORK_PORT)
@click.option('--message', help="A unicode message to encrypt for a policy", type=click.STRING)
@click.option('--policy-encrypting-key', help="Encrypting Public Key for Policy as hexidecimal string", type=click.STRING)
@nucypher_click_config
def enrico(click_config, action, policy_encrypting_key, dry_run, http_port, message):
    """
    "Enrico the Encryptor" management commands.

    \b
    Actions
    -------------------------------------------------
    \b
    run       Start Enrico's controller.
    encrypt   Encrypt a message under a given policy public key

    """

    #
    # Validate
    #

    if not policy_encrypting_key:
        raise click.BadArgumentUsage('--policy-encrypting-key is required to start Enrico.')

    # Banner
    emitter = click_config.emitter
    emitter.clear()
    emitter.banner(ENRICO_BANNER.format(policy_encrypting_key))

    #
    # Make Enrico
    #

    policy_encrypting_key = UmbralPublicKey.from_bytes(bytes.fromhex(policy_encrypting_key))
    ENRICO = Enrico(policy_encrypting_key=policy_encrypting_key)
    ENRICO.controller.emitter = emitter  # TODO: set it on object creation? Or not set at all?

    #
    # Actions
    #

    if action == 'run':

        # RPC
        if click_config.json_ipc:
            rpc_controller = ENRICO.make_rpc_controller()
            _transport = rpc_controller.make_control_transport()
            rpc_controller.start()
            return

        ENRICO.log.info('Starting HTTP Character Web Controller')
        controller = ENRICO.make_web_controller()
        return controller.start(http_port=http_port, dry_run=dry_run)

    elif action == 'encrypt':

        # Validate
        if not message:
            raise click.BadArgumentUsage('--message is a required flag to encrypt.')

        # Request
        encryption_request = {'message': message}
        response = ENRICO.controller.encrypt_message(request=encryption_request)
        return response

    else:
        raise click.BadArgumentUsage
