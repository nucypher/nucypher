import click

from hendrix.deploy.base import HendrixDeploy
from nucypher.characters.lawful import Enrico
from nucypher.cli.types import NETWORK_PORT
from umbral.keys import UmbralPublicKey

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
@click.option('--http-port', help="The host port to run Moe HTTP services on", type=NETWORK_PORT, default=5151)  # TODO
@click.option('--policy-encrypting-key', help="Encrypting Public Key for Policy as hexidecimal string", type=click.STRING)
def enrico(action, policy_encrypting_key, dry_run, http_port):
    """
    Start and manage an "Enrico" character control HTTP server
    """

    click.secho(ENRICO_BANNER.format(policy_encrypting_key))

    if action == 'run':  # Forest
        policy_encrypting_key = UmbralPublicKey.from_bytes(bytes.fromhex(policy_encrypting_key))
        ENRICO = Enrico(policy_encrypting_key=policy_encrypting_key)

        # Enrico Control
        enrico_control = ENRICO.make_wsgi_app()
        click.secho("Starting Enrico Character Control...")

        click.secho(f"Enrico Signing Key {bytes(ENRICO.stamp).hex()}", fg="green", bold=True)

        # Run
        if dry_run:
            return

        hx_deployer = HendrixDeploy(action="start", options={"wsgi": enrico_control, "http_port": http_port})
        hx_deployer.run()  # <--- Blocking Call to Reactor

    else:
        raise click.BadArgumentUsage
