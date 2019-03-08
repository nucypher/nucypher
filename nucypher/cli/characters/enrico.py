import click
from umbral.keys import UmbralPublicKey

from nucypher.characters.banners import ENRICO_BANNER
from nucypher.characters.control.emitters import IPCStdoutEmitter
from nucypher.characters.lawful import Enrico
from nucypher.cli.config import nucypher_click_config
from nucypher.cli.types import NETWORK_PORT


@click.command()
@click.argument('action')
@click.option('--dry-run', '-x', help="Execute normally without actually starting the node", is_flag=True)
@click.option('--http-port', help="The host port to run Moe HTTP services on", type=NETWORK_PORT, default=5151)  # TODO: default ports
@click.option('--message', help="A unicode message to encrypt for a policy", type=click.STRING)
@click.option('--policy-encrypting-key', help="Encrypting Public Key for Policy as hexidecimal string", type=click.STRING)
@nucypher_click_config
def enrico(click_config, action, policy_encrypting_key, dry_run, http_port, message):
    """
    Start and manage an "Enrico" character control HTTP server
    """

    if not policy_encrypting_key:
        raise click.BadArgumentUsage('--policy-encrypting-key is required to start Enrico.')

    if not click_config.json_ipc and not click_config.quiet:
        click.secho(ENRICO_BANNER)

    policy_encrypting_key = UmbralPublicKey.from_bytes(bytes.fromhex(policy_encrypting_key))
    ENRICO = Enrico(policy_encrypting_key=policy_encrypting_key)

    if click_config.json_ipc:
        ENRICO.controller.emitter = IPCStdoutEmitter(quiet=click_config.quiet)

    if action == 'run':  # Forrest
        controller = ENRICO.make_web_controller()
        ENRICO.log.info('Starting HTTP Character Web Controller')
        return controller.start(http_port=http_port, dry_run=dry_run)

    elif action == 'encrypt':
        if not message:
            raise click.BadArgumentUsage('--message is a required flag to encrypt.')

        encryption_request = {'message': message}

        response = ENRICO.controller.encrypt_message(request=encryption_request)
        return response

    else:
        raise click.BadArgumentUsage
