

import maya
import pytest
import pytest_twisted as pt
from twisted.internet.threads import deferToThread


@pt.inlineCallbacks
def test_one_node_stores_a_bunch_of_others(ursulas, lonely_ursula_maker):
    the_chosen_seednode = list(ursulas)[2]  # ...neo?
    seed_node = the_chosen_seednode.seed_node_metadata()

    newcomer = lonely_ursula_maker(
        quantity=1,
        save_metadata=True,
        seed_nodes=[seed_node]).pop()

    assert not newcomer.known_nodes

    newcomer.start_learning_loop(now=True)

    def start_lonely_learning_loop():
        newcomer.start_learning_loop()
        start = maya.now()
        # Loop until the_chosen_seednode is in storage.
        while the_chosen_seednode.checksum_address not in [
            u.checksum_address for u in newcomer.node_storage.all()
        ]:
            passed = maya.now() - start
            if passed.seconds > 2:
                pytest.fail("Didn't find the seed node.")

    yield deferToThread(start_lonely_learning_loop)

    matured_known_nodes = list(node.mature() for node in newcomer.known_nodes)
    assert list(matured_known_nodes)
    assert len(matured_known_nodes) == len(
        list(newcomer.node_storage.all())
    )  # TODO: why are certificates note being stored here?
    assert set(matured_known_nodes) == set(list(newcomer.node_storage.all()))
