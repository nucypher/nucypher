import os
import tempfile
from pathlib import Path

import pytest_twisted
import requests
from cryptography.hazmat.primitives import serialization
from twisted.internet import threads

from tests.utils.ursula import make_decentralized_ursulas


@pytest_twisted.inlineCallbacks
def test_ursula_serves_statics(ursula_decentralized_test_config, testerchain, agency):

    with tempfile.TemporaryDirectory() as STATICS_DIR:
        os.environ['NUCYPHER_STATIC_FILES_ROOT'] = str(STATICS_DIR)

        node = make_decentralized_ursulas(
            ursula_config=ursula_decentralized_test_config,
            quantity=1,
            staking_provider_addresses=testerchain.stake_providers_accounts,
            operator_addresses=testerchain.ursulas_accounts,
        ).pop()
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
