from constant_sorrow.constants import FLEET_STATES_MATCH, NO_KNOWN_NODES
from hendrix.experience import crosstown_traffic
from hendrix.utils.test_utils import crosstownTaskListDecoratorFactory
from nucypher.utilities.sandbox.ursula import make_federated_ursulas
from functools import partial


def test_learning_from_node_with_no_known_nodes(ursula_federated_test_config):
    lonely_ursula_maker = partial(make_federated_ursulas,
                                  ursula_config=ursula_federated_test_config,
                                  quantity=1,
                                  know_each_other=False)
    lonely_teacher = lonely_ursula_maker().pop()
    lonely_learner = lonely_ursula_maker(known_nodes=[lonely_teacher]).pop()

    learning_callers = []
    crosstown_traffic.decorator = crosstownTaskListDecoratorFactory(learning_callers)

    result = lonely_learner.learn_from_teacher_node()
    assert result is NO_KNOWN_NODES


def test_all_nodes_have_same_fleet_state(federated_ursulas):
    checksums = [u.known_nodes.checksum for u in federated_ursulas]
    assert len(set(checksums)) == 1  # There is only 1 unique value.


def test_teacher_nodes_cycle(federated_ursulas):
    ursula = list(federated_ursulas)[0]

    # Before we start learning, Ursula has no teacher.
    assert ursula._current_teacher_node is None

    # Once we start, Ursula picks a teacher node.
    ursula.learn_from_teacher_node()
    first_teacher = ursula._current_teacher_node

    # When she learns the second time, it's from a different teacher.
    ursula.learn_from_teacher_node()
    second_teacher = ursula._current_teacher_node

    assert first_teacher != second_teacher


def test_nodes_with_equal_fleet_state_do_not_send_anew(federated_ursulas):
    some_ursula = list(federated_ursulas)[2]
    another_ursula = list(federated_ursulas)[3]

    # These two have the same fleet state.
    assert some_ursula.known_nodes.checksum == another_ursula.known_nodes.checksum
    some_ursula._current_teacher_node = another_ursula
    result = some_ursula.learn_from_teacher_node()
    assert result is FLEET_STATES_MATCH


def test_old_state_is_preserved(federated_ursulas, ursula_federated_test_config):
    lonely_ursula_maker = partial(make_federated_ursulas,
                                  ursula_config=ursula_federated_test_config,
                                  quantity=1,
                                  know_each_other=False)
    lonely_learner = lonely_ursula_maker().pop()

    # This Ursula doesn't know about any nodes.
    assert len(lonely_learner.known_nodes) == 0

    some_ursula_in_the_fleet = list(federated_ursulas)[0]
    lonely_learner.remember_node(some_ursula_in_the_fleet)
    checksum_after_learning_one = lonely_learner.known_nodes.checksum

    another_ursula_in_the_fleet = list(federated_ursulas)[1]
    lonely_learner.remember_node(another_ursula_in_the_fleet)
    checksum_after_learning_two = lonely_learner.known_nodes.checksum

    assert checksum_after_learning_one != checksum_after_learning_two

    proper_first_state = sorted([some_ursula_in_the_fleet, lonely_learner], key=lambda n: n.checksum_address)
    assert lonely_learner.known_nodes.states[checksum_after_learning_one].nodes == proper_first_state

    proper_second_state = sorted([some_ursula_in_the_fleet, another_ursula_in_the_fleet, lonely_learner],
                                 key=lambda n: n.checksum_address)
    assert lonely_learner.known_nodes.states[checksum_after_learning_two].nodes == proper_second_state


def test_state_is_recorded_after_learning(federated_ursulas, ursula_federated_test_config):
    """
    Similar to above, but this time we show that the Learner records a new state only once after learning
    about a bunch of nodes.
    """
    lonely_ursula_maker = partial(make_federated_ursulas,
                                  ursula_config=ursula_federated_test_config,
                                  quantity=1,
                                  know_each_other=False)
    lonely_learner = lonely_ursula_maker().pop()

    # This Ursula doesn't know about any nodes.
    assert len(lonely_learner.known_nodes) == 0

    some_ursula_in_the_fleet = list(federated_ursulas)[0]
    lonely_learner.remember_node(some_ursula_in_the_fleet)

    # The rest of the fucking owl.
    lonely_learner.learn_from_teacher_node()

    states = list(lonely_learner.known_nodes.states.values())
    assert len(states) == 2

    assert len(states[0].nodes) == 2  # This and one other.
    assert len(states[1].nodes) == len(federated_ursulas) + 1  # Again, accounting for this Learner.
