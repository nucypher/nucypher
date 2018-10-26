from functools import partial

import maya
import pytest
import pytest_twisted
from twisted.internet.threads import deferToThread

from nucypher.network.middleware import RestMiddleware
from nucypher.utilities.sandbox.ursula import make_federated_ursulas
from cryptography.hazmat.primitives import serialization


def test_proper_seed_node_instantiation(ursula_federated_test_config):
    lonely_ursula_maker = partial(make_federated_ursulas,
                                  ursula_config=ursula_federated_test_config,
                                  quantity=1,
                                  know_each_other=False)

    firstula = lonely_ursula_maker().pop()
    firstula_as_seed_node = firstula.seed_node_metadata()
    any_other_ursula = lonely_ursula_maker(seed_nodes=[firstula_as_seed_node]).pop()

    assert not any_other_ursula.known_nodes
    any_other_ursula.start_learning_loop(now=True)
    assert firstula in any_other_ursula.known_nodes.values()


@pytest_twisted.inlineCallbacks
def test_get_cert_from_running_seed_node(ursula_federated_test_config):
    lonely_ursula_maker = partial(make_federated_ursulas,
                                  ursula_config=ursula_federated_test_config,
                                  quantity=1,
                                  know_each_other=False)
    firstula = lonely_ursula_maker().pop()
    node_deployer = firstula.get_deployer()

    node_deployer.addServices()
    node_deployer.catalogServers(node_deployer.hendrix)
    node_deployer.start()

    cert = node_deployer.cert.to_cryptography()
    cert_bytes = cert.public_bytes(serialization.Encoding.PEM)

    firstula_as_seed_node = firstula.seed_node_metadata()
    any_other_ursula = lonely_ursula_maker(seed_nodes=[firstula_as_seed_node],
                                           network_middleware=RestMiddleware()).pop()
    assert not any_other_ursula.known_nodes

    def start_lonely_learning_loop():
        any_other_ursula.start_learning_loop()
        start = maya.now()
        while not firstula in any_other_ursula.known_nodes.values():
            passed = maya.now() - start
            if passed.seconds > 2:
                pytest.fail("Didn't find the seed node.")

    yield deferToThread(start_lonely_learning_loop)
    assert firstula in any_other_ursula.known_nodes.values()
