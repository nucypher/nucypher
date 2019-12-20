import click
from umbral.keys import UmbralPublicKey

from nucypher.characters.banners import ENRICO_BANNER
from nucypher.characters.lawful import Enrico
from nucypher.cli.config import nucypher_click_config
from nucypher.cli.types import NETWORK_PORT


policy_encrypting_key_option =  \
    click.option('--policy-encrypting-key', help="Encrypting Public Key for Policy as hexadecimal string",
                 type=click.STRING, required=True)


@click.group()
def enrico():
    """
    "Enrico the Encryptor" management commands.
    """
    pass


@enrico.command()
@policy_encrypting_key_option
@click.option('--dry-run', '-x', help="Execute normally without actually starting the node", is_flag=True)
@click.option('--http-port', help="The host port to run Enrico HTTP services on", type=NETWORK_PORT)
@nucypher_click_config
def run(click_config, policy_encrypting_key, dry_run, http_port):
    """
    Start Enrico's controller.
    """

    ### Setup ###
    emitter = _setup_emitter(click_config, policy_encrypting_key)

    ENRICO = _create_enrico(emitter, policy_encrypting_key)
    #############

    # RPC
    if click_config.json_ipc:
        rpc_controller = ENRICO.make_rpc_controller()
        _transport = rpc_controller.make_control_transport()
        rpc_controller.start()
        return

    ENRICO.log.info('Starting HTTP Character Web Controller')
    controller = ENRICO.make_web_controller()
    return controller.start(http_port=http_port, dry_run=dry_run)


@enrico.command()
@policy_encrypting_key_option
@click.option('--message', help="A unicode message to encrypt for a policy", type=click.STRING, required=True)
@nucypher_click_config
def encrypt(click_config, policy_encrypting_key, message):
    """
    Encrypt a message under a given policy public key.
    """

    ### Setup ###
    emitter = _setup_emitter(click_config, policy_encrypting_key)

    ENRICO = _create_enrico(emitter, policy_encrypting_key)
    #############

    # Request
    encryption_request = {'message': message}
    response = ENRICO.controller.encrypt_message(request=encryption_request)
    return response


def _setup_emitter(click_config, policy_encrypting_key):
    emitter = click_config.emitter
    emitter.clear()
    emitter.banner(ENRICO_BANNER.format(policy_encrypting_key))

    return emitter


def _create_enrico(emitter, policy_encrypting_key):
    policy_encrypting_key = UmbralPublicKey.from_bytes(bytes.fromhex(policy_encrypting_key))
    ENRICO = Enrico(policy_encrypting_key=policy_encrypting_key)
    ENRICO.controller.emitter = emitter  # TODO: set it on object creation? Or not set at all?

    return ENRICO
