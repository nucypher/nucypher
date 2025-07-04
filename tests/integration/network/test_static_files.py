import os

import pytest_twisted
import requests
from cryptography.hazmat.primitives import serialization
from twisted.internet import threads

from tests.utils.ursula import cleanup_ursulas, make_reserved_ursulas


@pytest_twisted.inlineCallbacks
def test_ursula_serves_statics(ursula_test_config, accounts, mocker, temp_dir_path):
    original_getenv = os.getenv

    # mock the environment variable to point to the temporary directory
    def mock_getenv(key, default=None):
        if key == "NUCYPHER_STATIC_FILES_ROOT":
            return str(temp_dir_path)
        return original_getenv(key, default)

    mocker.patch("os.getenv", side_effect=mock_getenv)

    node = make_reserved_ursulas(
        accounts=accounts,
        ursula_config=ursula_test_config,
        quantity=1,
    ).pop()
    try:
        node_deployer = node.get_deployer()

        node_deployer.addServices()
        node_deployer.catalogServers(node_deployer.hendrix)
        node_deployer.start()

        cert = node_deployer.cert.to_cryptography()
        cert_bytes = cert.public_bytes(serialization.Encoding.PEM)

        def check_static_service(node, cert_file):

            response = requests.get(
                "https://{}/statics/test-never-make-a-file-with-this-name.js".format(
                    node.rest_url()
                ),
                verify=cert_file,
            )
            assert response.status_code == 200
            assert "I am Javascript" in response.text
            return node

        def check_static_file_not_there(node, cert_file):

            response = requests.get(
                "https://{}/statics/no-file-by-this-name.js".format(node.rest_url()),
                verify=cert_file,
            )
            assert response.status_code == 404
            return node

        cert_file = temp_dir_path / "test-cert"

        with open(cert_file, "wb") as f:
            f.write(cert_bytes)

        temp_dir_path.mkdir(exist_ok=True)
        with open(
            temp_dir_path / "test-never-make-a-file-with-this-name.js", "w+"
        ) as fout:
            fout.write("console.log('I am Javascript')\n")
            fout.close()

        yield threads.deferToThread(check_static_service, node, cert_file)
        yield threads.deferToThread(check_static_file_not_there, node, cert_file)
    finally:
        cleanup_ursulas([node])
