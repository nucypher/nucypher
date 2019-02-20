import json
import os.path

import click
from constant_sorrow import constants
from flask import Flask, render_template
from hendrix.deploy.base import HendrixDeploy
from hendrix.experience import hey_joe

from nucypher.characters.banners import MOE_BANNER
from nucypher.characters.chaotic import Moe
from nucypher.characters.lawful import Ursula
from nucypher.cli.types import NETWORK_PORT
from nucypher.network.middleware import RestMiddleware


@click.command()
@click.option('--teacher-uri', help="An Ursula URI to start learning from (seednode)", type=click.STRING)
@click.option('--min-stake', help="The minimum stake the teacher must have to be a teacher", type=click.INT, default=0)
@click.option('--network', help="Network Domain Name", type=click.STRING)
@click.option('--http-port', help="The host port to run Moe HTTP services on", type=NETWORK_PORT, default=12500)
@click.option('--ws-port', help="The host port to run websocket network services on", type=NETWORK_PORT, default=9000)
@click.option('--dry-run', '-x', help="Execute normally without actually starting the node", is_flag=True)
@click.option('--learn-on-launch', help="Conduct first learning loop on main thread at launch.", is_flag=True)
def moe(teacher_uri, min_stake, network, ws_port, dry_run, http_port, learn_on_launch):

    """
    "Moe" NuCypher node monitor CLI.
    """

    click.secho(MOE_BANNER)

    #
    # Teacher
    #

    teacher_nodes = list()
    if teacher_uri:
        teacher_node = Ursula.from_seed_and_stake_info(seed_uri=teacher_uri,
                                                       federated_only=True,
                                                       minimum_stake=min_stake)
        teacher_nodes.append(teacher_node)

    # Deserialize network domain name if override passed
    if network:
        domain_constant = getattr(constants, network.upper())
        domains = {domain_constant}
    else:
        domains = None

    monitor = Moe(
        domains=domains,
        network_middleware=RestMiddleware(),
        known_nodes=teacher_nodes,
        federated_only=True,
    )

    monitor.start_learning_loop(now=learn_on_launch)

    #
    # Websocket Service
    #

    def send_states(subscriber):
        message = ["states", monitor.known_nodes.abridged_states_dict()]
        subscriber.sendMessage(json.dumps(message).encode())

    def send_nodes(subscriber):
        message = ["nodes", monitor.known_nodes.abridged_nodes_dict()]
        subscriber.sendMessage(json.dumps(message).encode())

    websocket_service = hey_joe.WebSocketService("127.0.0.1", ws_port)
    websocket_service.register_followup("states", send_states)
    websocket_service.register_followup("nodes", send_nodes)

    #
    # Flask App
    #

    rest_app = Flask("fleet-monitor", root_path=os.path.dirname(__file__))

    @rest_app.route("/")
    def status():
        template_path = os.path.join('monitor.html')
        return render_template(template_path)

    #
    # Server
    #

    deployer = HendrixDeploy(action="start", options={"wsgi": rest_app, "http_port": http_port})
    deployer.add_non_tls_websocket_service(websocket_service)

    click.secho(f"Running Moe on 127.0.0.1:{http_port}")

    if not dry_run:
        deployer.run()
