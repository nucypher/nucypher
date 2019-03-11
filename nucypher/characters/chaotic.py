import json
import os

import click
from flask import Flask, render_template
from hendrix.deploy.base import HendrixDeploy
from hendrix.experience import hey_joe

from nucypher.characters.banners import MOE_BANNER
from nucypher.characters.base import Character
from nucypher.config.constants import TEMPLATES_DIR
from nucypher.network.nodes import FleetStateTracker


class Moe(Character):
    """
    A monitor (lizard?)
    """
    banner = MOE_BANNER

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.log.info(self.banner)

    class MonitoringTracker(FleetStateTracker):
        def record_fleet_state(self, *args, **kwargs):
            new_state_or_none = super().record_fleet_state(*args, **kwargs)
            if new_state_or_none:
                checksum, new_state = new_state_or_none
                hey_joe.send({checksum: self.abridged_state_details(new_state)}, "states")
            return new_state_or_none

    tracker_class = MonitoringTracker
    _SHORT_LEARNING_DELAY = .5
    _LONG_LEARNING_DELAY = 30
    LEARNING_TIMEOUT = 10
    _ROUNDS_WITHOUT_NODES_AFTER_WHICH_TO_SLOW_DOWN = 25

    def remember_node(self, *args, **kwargs):
        new_node_or_none = super().remember_node(*args, **kwargs)
        if new_node_or_none:
            hey_joe.send(
                {new_node_or_none.checksum_public_address: Moe.MonitoringTracker.abridged_node_details(new_node_or_none)},
                "nodes")
        return new_node_or_none

    def learn_from_teacher_node(self, *args, **kwargs):
        teacher = self.current_teacher_node(cycle=False)
        new_nodes = super().learn_from_teacher_node(*args, **kwargs)
        hey_joe.send({teacher.checksum_public_address: Moe.MonitoringTracker.abridged_node_details(teacher)}, "nodes")
        new_teacher = self.current_teacher_node(cycle=False)
        hey_joe.send({"current_teacher": new_teacher.checksum_public_address}, "teachers")
        return new_nodes

    def start(self, ws_port: int, http_port: int, dry_run: bool = False):

        #
        # Websocket Service
        #

        def send_states(subscriber):
            message = ["states", self.known_nodes.abridged_states_dict()]
            subscriber.sendMessage(json.dumps(message).encode())

        def send_nodes(subscriber):
            message = ["nodes", self.known_nodes.abridged_nodes_dict()]
            subscriber.sendMessage(json.dumps(message).encode())

        websocket_service = hey_joe.WebSocketService("127.0.0.1", ws_port)
        websocket_service.register_followup("states", send_states)
        websocket_service.register_followup("nodes", send_nodes)

        #
        # WSGI Service
        #

        self.rest_app = Flask("fleet-monitor", template_folder=TEMPLATES_DIR)
        rest_app = self.rest_app

        @rest_app.route("/")
        def status():
            try:
                return render_template('monitor.html')
            except Exception as e:
                self.log.debug(str(e))

        #
        # Server
        #

        deployer = HendrixDeploy(action="start", options={"wsgi": rest_app, "http_port": http_port})
        deployer.add_non_tls_websocket_service(websocket_service)

        click.secho(f"Running Moe on 127.0.0.1:{http_port}")

        if not dry_run:
            deployer.run()
