import click

from nucypher.characters.banners import MOE_BANNER
from nucypher.characters.chaotic import Moe
from nucypher.cli import actions
from nucypher.cli.config import nucypher_click_config
from nucypher.cli.types import NETWORK_PORT
from nucypher.network.middleware import RestMiddleware


@click.command()
@click.option('--teacher', 'teacher_uri', help="An Ursula URI to start learning from (seednode)", type=click.STRING)
@click.option('--min-stake', help="The minimum stake the teacher must have to be a teacher", type=click.INT, default=0)
@click.option('--network', help="Network Domain Name", type=click.STRING)
@click.option('--http-port', help="The host port to run Moe HTTP services on", type=NETWORK_PORT)
@click.option('--ws-port', help="The host port to run websocket network services on", type=NETWORK_PORT)
@click.option('--dry-run', '-x', help="Execute normally without actually starting the node", is_flag=True)
@click.option('--learn-on-launch', help="Conduct first learning loop on main thread at launch.", is_flag=True)
@nucypher_click_config
def moe(click_config, teacher_uri, min_stake, network, ws_port, dry_run, http_port, learn_on_launch):
    """
    "Moe the Monitor" management commands.
    """

    emitter = click_config.emitter

    # Banner
    emitter.clear()
    emitter.banner(MOE_BANNER)

    # Teacher Ursula
    teacher_uris = [teacher_uri] if teacher_uri else None
    teacher_nodes = actions.load_seednodes(emitter,
                                           teacher_uris=teacher_uris,
                                           min_stake=min_stake,
                                           federated_only=True,    # TODO: hardcoded for now.  Is Moe a Character?
                                           network_domains={network} if network else None,
                                           network_middleware=click_config.middleware)

    # Make Moe
    MOE = Moe(domains={network} if network else None,
              network_middleware=RestMiddleware(),
              known_nodes=teacher_nodes,
              federated_only=True)

    # Run
    MOE.start_learning_loop(now=learn_on_launch)

    emitter.message(f"Running Moe on 127.0.0.1:{http_port}")

    MOE.start(http_port=http_port, ws_port=ws_port, dry_run=dry_run)
