import json
import os.path

import click
from constant_sorrow import constants
from flask import Flask, render_template
from twisted.logger import globalLogPublisher

from hendrix.deploy.base import HendrixDeploy
from hendrix.experience import hey_joe
from nucypher.characters.base import Character
from nucypher.characters.lawful import Ursula
from nucypher.cli.types import NETWORK_PORT
from nucypher.network.middleware import RestMiddleware
from nucypher.network.nodes import FleetStateTracker
from nucypher.utilities.logging import SimpleObserver


globalLogPublisher.addObserver(SimpleObserver())

MOE_BANNER = r"""
 _______               
|   |   |.-----..-----.
|       ||  _  ||  -__|
|__|_|__||_____||_____|

the Monitor.
"""


class MonitoringTracker(FleetStateTracker):
    def record_fleet_state(self, *args, **kwargs):
        new_state_or_none = super(MonitoringTracker, self).record_fleet_state(*args, **kwargs)
        if new_state_or_none:
            checksum, new_state = new_state_or_none
            hey_joe.send({checksum: self.abridged_state_details(new_state)}, "states")
        return new_state_or_none


class Moe(Character):
    """
    A monitor (lizard?)
    """
    tracker_class = MonitoringTracker
    _SHORT_LEARNING_DELAY = .5
    _LONG_LEARNING_DELAY = 30
    LEARNING_TIMEOUT = 10
    _ROUNDS_WITHOUT_NODES_AFTER_WHICH_TO_SLOW_DOWN = 25

    def remember_node(self, *args, **kwargs):
        new_node_or_none = super().remember_node(*args, **kwargs)
        if new_node_or_none:
            hey_joe.send(
                {new_node_or_none.checksum_public_address: MonitoringTracker.abridged_node_details(new_node_or_none)},
                "nodes")
        return new_node_or_none

    def learn_from_teacher_node(self, *args, **kwargs):
        teacher = self.current_teacher_node(cycle=False)
        new_nodes = super().learn_from_teacher_node(*args, **kwargs)
        hey_joe.send({teacher.checksum_public_address: MonitoringTracker.abridged_node_details(teacher)}, "nodes")
        new_teacher = self.current_teacher_node(cycle=False)
        hey_joe.send({"current_teacher": new_teacher.checksum_public_address}, "teachers")
        return new_nodes


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
