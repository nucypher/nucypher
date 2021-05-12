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
from pathlib import Path

import pytest_twisted
import requests
from cryptography.hazmat.primitives import serialization
from twisted.internet import threads
from tests.utils.ursula import make_federated_ursulas


@pytest_twisted.inlineCallbacks
def test_ursula_serves_statics(ursula_federated_test_config):

    with tempfile.TemporaryDirectory() as STATICS_DIR:
        os.environ['NUCYPHER_STATIC_FILES_ROOT'] = STATICS_DIR

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
            assert response.headers['Content-Type'] == 'application/javascript'
            return node

        def check_static_file_not_there(node, cert_file):

            response = requests.get(
                "https://{}/statics/no-file-by-this-name.js".format(node.rest_url()),
                verify=cert_file
            )
            assert response.status_code == 404
            return node

        try:
            with open("test-cert", "wb") as f:
                f.write(cert_bytes)
            Path(STATICS_DIR).mkdir(exist_ok=True)
            with open(Path(STATICS_DIR, 'test-never-make-a-file-with-this-name.js'), 'w+') as fout:
                fout.write("console.log('I am Javascript')\n")
                fout.close()
            yield threads.deferToThread(check_static_service, node, "test-cert")
            yield threads.deferToThread(check_static_file_not_there, node, "test-cert")
        finally:
            Path("test-cert").unlink()
