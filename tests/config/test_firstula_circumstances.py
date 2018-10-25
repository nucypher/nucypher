from functools import partial

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
    any_other_ursula.start_learning_loop()
    assert firstula in any_other_ursula.known_nodes.values()
