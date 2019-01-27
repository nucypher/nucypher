import sys

from flask import Flask, render_template
from twisted.logger import globalLogPublisher

from hendrix.deploy.base import HendrixDeploy
from hendrix.experience import crosstown_traffic, hey_joe
from nucypher.characters.base import Character
from nucypher.characters.lawful import Ursula
from nucypher.config.constants import GLOBAL_DOMAIN
from nucypher.network.middleware import RestMiddleware
from nucypher.network.nodes import FleetStateTracker
from nucypher.utilities.logging import SimpleObserver

websocket_service = hey_joe.WebSocketService("127.0.0.1", 9000)
globalLogPublisher.addObserver(SimpleObserver())

known_node = Ursula.from_seed_and_stake_info(seed_uri=sys.argv[1],
                                             federated_only=True,
                                             minimum_stake=0)

rest_app = Flask("fleet-monitor")


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


monitor = Moe(
    domains=GLOBAL_DOMAIN,
    network_middleware=RestMiddleware(),
    known_nodes=[known_node],
    federated_only=True,
)

monitor.start_learning_loop()

import time
import json


def send_states(subscriber):
    message = ["states", monitor.known_nodes.abridged_states_dict()]
    subscriber.sendMessage(json.dumps(message).encode())


websocket_service.register_followup("states", send_states)


@rest_app.route("/")
def status():


        # for node in monitor.known_nodes:
        #     hey_joe.send(node.status_json(), topic="nodes")

    return render_template('monitor.html')


deployer = HendrixDeploy(action="start", options={"wsgi": rest_app, "http_port": 9750})
deployer.add_non_tls_websocket_service(websocket_service)
deployer.run()
