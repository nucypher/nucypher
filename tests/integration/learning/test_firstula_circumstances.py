from functools import partial

import pytest_twisted as pt
from twisted.internet.threads import deferToThread

from nucypher.config.constants import TEMPORARY_DOMAIN
from nucypher.network.middleware import RestMiddleware
from tests.constants import MOCK_ETH_PROVIDER_URI


def test_proper_seed_node_instantiation(lonely_ursula_maker):
    _lonely_ursula_maker = partial(lonely_ursula_maker, quantity=1)
    firstula = _lonely_ursula_maker(domain=TEMPORARY_DOMAIN).pop()
    firstula_as_seed_node = firstula.seed_node_metadata()
    any_other_ursula = _lonely_ursula_maker(
        seed_nodes=[firstula_as_seed_node], domain=TEMPORARY_DOMAIN
    ).pop()

    assert not any_other_ursula.known_nodes
    any_other_ursula.start_learning_loop(now=True)
    assert firstula in any_other_ursula.known_nodes


@pt.inlineCallbacks
def test_get_cert_from_running_seed_node(lonely_ursula_maker):

    firstula = lonely_ursula_maker().pop()
    node_deployer = firstula.get_deployer()

    node_deployer.addServices()
    node_deployer.catalogServers(node_deployer.hendrix)
    node_deployer.start()   # If this port happens not to be open, we'll get an error here.  THis might be one of the few sane places to reintroduce a check.

    certificate_as_deployed = node_deployer.cert.to_cryptography()

    firstula_as_seed_node = firstula.seed_node_metadata()
    any_other_ursula = lonely_ursula_maker(
        seed_nodes=[firstula_as_seed_node],
        network_middleware=RestMiddleware(eth_endpoint=MOCK_ETH_PROVIDER_URI),
    ).pop()
    assert not any_other_ursula.known_nodes

    yield deferToThread(lambda: any_other_ursula.load_seednodes(record_fleet_state=True))
    assert firstula in any_other_ursula.known_nodes

    firstula_as_learned = any_other_ursula.known_nodes[firstula.checksum_address]
    firstula_as_learned.mature()
    assert certificate_as_deployed == firstula_as_learned.certificate
