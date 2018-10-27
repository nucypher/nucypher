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
