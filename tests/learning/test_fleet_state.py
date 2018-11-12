from constant_sorrow.constants import FLEET_STATES_MATCH


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