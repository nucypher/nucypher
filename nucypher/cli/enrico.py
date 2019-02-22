import click
from umbral.keys import UmbralPublicKey

from nucypher.characters.lawful import Enrico
from nucypher.cli.types import NETWORK_PORT

ENRICO_BANNER = r"""
 ___                
 )_  _   _ o  _  _  
(__ ) ) )  ( (_ (_) 

the Encryptor.

{}
"""


@click.command()
@click.argument('action')
@click.option('--dry-run', '-x', help="Execute normally without actually starting the node", is_flag=True)
@click.option('--http-port', help="The host port to run Moe HTTP services on", type=NETWORK_PORT, default=5151)  # TODO: default ports
@click.option('--policy-encrypting-key', help="Encrypting Public Key for Policy as hexidecimal string", type=click.STRING)
def enrico(action, policy_encrypting_key, dry_run, http_port):
    """
    Start and manage an "Enrico" character control HTTP server
    """

    click.secho(ENRICO_BANNER.format(policy_encrypting_key))

    if action == 'run':  # Forest
        policy_encrypting_key = UmbralPublicKey.from_bytes(bytes.fromhex(policy_encrypting_key))
        ENRICO = Enrico(policy_encrypting_key=policy_encrypting_key)
        ENRICO.control.start_wsgi_conrol(http_port=http_port, dry_run=dry_run)

    else:
        raise click.BadArgumentUsage
