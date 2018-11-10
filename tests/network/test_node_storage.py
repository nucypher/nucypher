"""
This file is part of nucypher.

nucypher is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

nucypher is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with nucypher.  If not, see <https://www.gnu.org/licenses/>.
"""
import maya
import pytest
import pytest_twisted
from twisted.internet.threads import deferToThread

from nucypher.utilities.sandbox.ursula import make_federated_ursulas


@pytest_twisted.inlineCallbacks
def test_one_node_stores_a_bunch_of_others(federated_ursulas, ursula_federated_test_config):
    the_chosen_seednode = list(federated_ursulas)[2]
    seed_node = the_chosen_seednode.seed_node_metadata()
    newcomer = make_federated_ursulas(
        ursula_config=ursula_federated_test_config,
        quantity=1,
        know_each_other=False,
        save_metadata=True,
        seed_nodes=[seed_node]).pop()

    assert not newcomer.known_nodes

    def start_lonely_learning_loop():
        newcomer.start_learning_loop()
        start = maya.now()
        # Loop until the_chosen_seednode is in storage.
        while not the_chosen_seednode in newcomer.node_storage.all(federated_only=True):
            passed = maya.now() - start
            if passed.seconds > 2:
                pytest.fail("Didn't find the seed node.")

    yield deferToThread(start_lonely_learning_loop)

    # The known_nodes are all saved in storage (and no others have been saved)
    assert list(newcomer.known_nodes.values()) == list(newcomer.node_storage.all(True))
