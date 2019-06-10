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

from functools import partial

import pytest_twisted as pt
from twisted.internet.threads import deferToThread

from nucypher.network.middleware import RestMiddleware
from nucypher.utilities.sandbox.ursula import make_federated_ursulas


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
    assert firstula in any_other_ursula.known_nodes


@pt.inlineCallbacks
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

    certificate_as_deployed = node_deployer.cert.to_cryptography()

    firstula_as_seed_node = firstula.seed_node_metadata()
    any_other_ursula = lonely_ursula_maker(seed_nodes=[firstula_as_seed_node],
                                           network_middleware=RestMiddleware()).pop()
    assert not any_other_ursula.known_nodes

    def start_lonely_learning_loop():
        any_other_ursula.log.info(
            "Known nodes when starting learning loop were: {}".format(any_other_ursula.known_nodes))
        any_other_ursula.start_learning_loop()
        result = any_other_ursula.block_until_specific_nodes_are_known(set([firstula.checksum_address]),
                                                                       timeout=2)
        assert result

    yield deferToThread(start_lonely_learning_loop)
    assert firstula in any_other_ursula.known_nodes

    firstula_as_learned = any_other_ursula.known_nodes[firstula.checksum_address]
    assert certificate_as_deployed == firstula_as_learned.certificate
