import os
import pytest_twisted
import requests
from cryptography.hazmat.primitives import serialization
from twisted.internet import threads

from nucypher.characters.lawful import Ursula
from nucypher.utilities.sandbox.ursula import make_federated_ursulas


def test_alice_enacts_policies_in_policy_group_via_rest(enacted_federated_policy):
    """
    Now that Alice has made a PolicyGroup, she can enact its policies, using Ursula's Public Key to encrypt each offer
    and transmitting them via REST.
    """
    arrangement = list(enacted_federated_policy._accepted_arrangements)[0]
    ursula = arrangement.ursula
    policy_arrangement = ursula.datastore.get_policy_arrangement(arrangement.id.hex().encode())
    assert bool(policy_arrangement)  # TODO: This can be a more poignant assertion.


@pytest_twisted.inlineCallbacks
def test_federated_nodes_connect_via_tls_and_verify(ursula_federated_test_config):
    node = make_federated_ursulas(ursula_config=ursula_federated_test_config, quantity=1).pop()
    node_deployer = node.get_deployer()

    node_deployer.addServices()
    node_deployer.catalogServers(node_deployer.hendrix)
    node_deployer.start()

    cert = node_deployer.cert.to_cryptography()
    cert_bytes = cert.public_bytes(serialization.Encoding.PEM)

    def check_node_with_cert(node, cert_file):
        response = requests.get("https://{}/public_information".format(node.rest_url()), verify=cert_file)
        ursula = Ursula.from_bytes(response.content, federated_only=True)
        assert ursula == node

    try:
        with open("test-cert", "wb") as f:
            f.write(cert_bytes)
        yield threads.deferToThread(check_node_with_cert, node, "test-cert")
    finally:
        os.remove("test-cert")
