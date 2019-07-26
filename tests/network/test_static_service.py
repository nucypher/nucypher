"""
This file is part of nucypher.

nucypher is free software: you can redistribute it and/or modify
it under the terms of the GNU Affero General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

nucypher is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU Affero General Public License for more details.

You should have received a copy of the GNU Affero General Public License
along with nucypher.  If not, see <https://www.gnu.org/licenses/>.
"""

import os
import tempfile
import pytest_twisted
import requests
from cryptography.hazmat.primitives import serialization
from twisted.internet import threads

from nucypher.characters.lawful import Ursula
from nucypher.characters.chaotic import Moe
from nucypher.network.middleware import RestMiddleware
from nucypher.utilities.sandbox.ursula import make_federated_ursulas
from nucypher.utilities.sandbox.constants import MOCK_URSULA_STARTING_PORT, select_test_port
from nucypher.config.constants import STATICS_DIR


@pytest_twisted.inlineCallbacks
def test_ursula_serves_statics(ursula_federated_test_config):
    node = make_federated_ursulas(ursula_config=ursula_federated_test_config, quantity=1).pop()
    node_deployer = node.get_deployer()

    node_deployer.addServices()
    node_deployer.catalogServers(node_deployer.hendrix)
    node_deployer.start()

    cert = node_deployer.cert.to_cryptography()
    cert_bytes = cert.public_bytes(serialization.Encoding.PEM)

    def check_static_service(node, cert_file):

        response = requests.get(
            "https://{}/statics/test-never-make-a-file-with-this-name.js".format(node.rest_url()),
            verify=cert_file
        )
        assert response.status_code == 200
        assert "I am Javascript" in response.text

        return node

    try:
        with open("test-cert", "wb") as f:
            f.write(cert_bytes)
        os.makedirs(os.path.join(STATICS_DIR), exist_ok=True)
        with open(os.path.join(STATICS_DIR, 'test-never-make-a-file-with-this-name.js'), 'w+') as fout:
            fout.write("console.log('I am Javascript')\n")
            fout.close()
        yield threads.deferToThread(check_static_service, node, "test-cert")
    finally:
        os.remove("test-cert")
        os.remove(os.path.join(STATICS_DIR, 'test-never-make-a-file-with-this-name.js'))


@pytest_twisted.inlineCallbacks
def test_moe_serves_statics(federated_ursulas):

    node = Moe(
        domains={':fake-domain:'},
        network_middleware=RestMiddleware(),
        known_nodes=federated_ursulas,
        federated_only=True,
        is_me=True,
    )
    # configure rest app without starting the server
    node.start(8122, 8123, dry_run=True)

    # now start it on the already running reactor
    node_deployer = node.get_deployer('127.0.0.1', 8123, options={"wsgi": node.rest_app})
    node_deployer.addServices()
    node_deployer.catalogServers(node_deployer.hendrix)
    node_deployer.start()

    def check_static_service(node):

        response = requests.get(
            "http://{}/statics/test-never-make-a-file-with-this-name.js".format(node.rest_url()),
        )
        assert response.status_code == 200
        assert "I am Javascript" in response.text

        return node

    try:
        os.makedirs(os.path.join(STATICS_DIR), exist_ok=True)
        with open(os.path.join(STATICS_DIR, 'test-never-make-a-file-with-this-name.js'), 'w+') as fout:
            fout.write("console.log('I am Javascript')\n")
            fout.close()
        yield threads.deferToThread(check_static_service, node)
    finally:
        os.remove(os.path.join(STATICS_DIR, 'test-never-make-a-file-with-this-name.js'))
