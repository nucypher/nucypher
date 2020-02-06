import click
from umbral.keys import UmbralPublicKey

from nucypher.characters.banners import ENRICO_BANNER
from nucypher.characters.lawful import Enrico
from nucypher.cli.config import group_general_config
from nucypher.cli.options import option_dry_run, option_policy_encrypting_key
from nucypher.cli.types import NETWORK_PORT
from nucypher.characters.control.interfaces import EnricoInterface


@click.group()
def enrico():
    """
    "Enrico the Encryptor" management commands.
    """
    pass


@enrico.command()
@option_policy_encrypting_key(required=True)
@option_dry_run
@click.option('--http-port', help="The host port to run Enrico HTTP services on", type=NETWORK_PORT)
@group_general_config
def run(general_config, policy_encrypting_key, dry_run, http_port):
    """
    Start Enrico's controller.
    """

    ### Setup ###
    emitter = _setup_emitter(general_config, policy_encrypting_key)

    ENRICO = _create_enrico(emitter, policy_encrypting_key)
    #############

    # RPC
    if general_config.json_ipc:
        rpc_controller = ENRICO.make_rpc_controller()
        _transport = rpc_controller.make_control_transport()
        rpc_controller.start()
        return

    ENRICO.log.info('Starting HTTP Character Web Controller')
    controller = ENRICO.make_web_controller()
    return controller.start(http_port=http_port, dry_run=dry_run)


@enrico.command()
@EnricoInterface.connect_cli('encrypt_message')
@group_general_config
def encrypt(general_config, policy_encrypting_key, message):
    """
    Encrypt a message under a given policy public key.
    """

    ### Setup ###
    emitter = _setup_emitter(general_config, policy_encrypting_key)

    ENRICO = _create_enrico(emitter, policy_encrypting_key)
    #############

    # Request
    encryption_request = {'message': message}
    response = ENRICO.controller.encrypt_message(request=encryption_request)
    return response


def _setup_emitter(general_config, policy_encrypting_key):
    emitter = general_config.emitter
    emitter.clear()
    emitter.banner(ENRICO_BANNER.format(policy_encrypting_key))

    return emitter


def _create_enrico(emitter, policy_encrypting_key):
    policy_encrypting_key = UmbralPublicKey.from_bytes(bytes.fromhex(policy_encrypting_key))
    ENRICO = Enrico(policy_encrypting_key=policy_encrypting_key)
    ENRICO.controller.emitter = emitter

    return ENRICO
