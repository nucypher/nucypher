from functools import partial

from constant_sorrow.constants import FLEET_STATES_MATCH


def test_all_nodes_have_same_fleet_state(ursulas):
    checksums = [u.known_nodes.checksum for u in ursulas]
    assert len(set(checksums)) == 1  # There is only 1 unique value.


def test_teacher_nodes_cycle(ursulas):
    ursula = list(ursulas)[0]

    # Before we start learning, Ursula has no teacher.
    assert ursula._current_teacher_node is None

    # Once we start, Ursula picks a teacher node.
    ursula.learn_from_teacher_node()
    first_teacher = ursula._current_teacher_node

    # When she learns the second time, it's from a different teacher.
    ursula.learn_from_teacher_node()
    second_teacher = ursula._current_teacher_node

    assert first_teacher != second_teacher


def test_nodes_with_equal_fleet_state_do_not_send_anew(ursulas):
    some_ursula = list(ursulas)[2]
    another_ursula = list(ursulas)[3]

    # These two have the same fleet state.
    assert some_ursula.known_nodes.checksum == another_ursula.known_nodes.checksum
    some_ursula._current_teacher_node = another_ursula
    result = some_ursula.learn_from_teacher_node()
    assert result is FLEET_STATES_MATCH


def test_old_state_is_preserved(ursulas, lonely_ursula_maker):
    lonely_learner = lonely_ursula_maker().pop()

    # This Ursula doesn't know about any nodes.
    assert len(lonely_learner.known_nodes) == 0

    some_ursula_in_the_fleet = list(ursulas)[0]
    lonely_learner.remember_node(some_ursula_in_the_fleet)
    checksum_after_learning_one = lonely_learner.known_nodes.checksum
    assert some_ursula_in_the_fleet in lonely_learner.known_nodes
    assert some_ursula_in_the_fleet.checksum_address in lonely_learner.known_nodes
    assert len(lonely_learner.known_nodes) == 1
    assert lonely_learner.known_nodes.population == 2

    another_ursula_in_the_fleet = list(ursulas)[1]
    lonely_learner.remember_node(another_ursula_in_the_fleet)
    checksum_after_learning_two = lonely_learner.known_nodes.checksum
    assert some_ursula_in_the_fleet in lonely_learner.known_nodes
    assert another_ursula_in_the_fleet in lonely_learner.known_nodes
    assert some_ursula_in_the_fleet.checksum_address in lonely_learner.known_nodes
    assert another_ursula_in_the_fleet.checksum_address in lonely_learner.known_nodes
    assert len(lonely_learner.known_nodes) == 2
    assert lonely_learner.known_nodes.population == 3

    assert checksum_after_learning_one != checksum_after_learning_two

    first_state = lonely_learner.known_nodes._archived_states[-2]
    assert first_state.population == 2
    assert first_state.checksum == checksum_after_learning_one

    second_state = lonely_learner.known_nodes._archived_states[-1]
    assert second_state.population == 3
    assert second_state.checksum == checksum_after_learning_two


def test_state_is_recorded_after_learning(ursulas, lonely_ursula_maker):
    """
    Similar to above, but this time we show that the Learner records a new state only once after learning
    about a bunch of nodes.
    """
    _lonely_ursula_maker = partial(lonely_ursula_maker, quantity=1)
    lonely_learner = _lonely_ursula_maker().pop()
    states = lonely_learner.known_nodes._archived_states

    # This Ursula doesn't know about any nodes.
    assert len(lonely_learner.known_nodes) == 0

    some_ursula_in_the_fleet = list(ursulas)[0]
    lonely_learner.remember_node(some_ursula_in_the_fleet)
    # Archived states at this point:
    # - inital one (empty, Ursula's metadata is not ready yet, no known nodes)
    # - the one created in Learner.__init__(). Metadata is still not ready, so it's the same
    #   as the previous one and is not recorded.
    # - the one created after Ursula learned about a remote node
    assert len(states) == 2

    # The first fleet state is just us and the one about whom we learned, which is part of the fleet.
    assert states[-1].population == 2

    # The rest of the fucking owl.
    lonely_learner.learn_from_teacher_node()

    # There are two new states: one created after seednodes are loaded, to select a teacher,
    # and the second after we get the rest of the nodes from the seednodes.
    assert len(states) == 4

    # When we ran learn_from_teacher_node, we also loaded the rest of the fleet.
    assert states[-1].population == len(ursulas) + 1


def test_teacher_records_new_fleet_state_upon_hearing_about_new_node(
    ursulas, lonely_ursula_maker
):
    _lonely_ursula_maker = partial(lonely_ursula_maker, quantity=1)
    lonely_learner = _lonely_ursula_maker().pop()

    some_ursula_in_the_fleet = list(ursulas)[0]

    lonely_learner.remember_node(some_ursula_in_the_fleet)

    states = some_ursula_in_the_fleet.known_nodes._archived_states

    states_before = len(states)
    lonely_learner.learn_from_teacher_node()
    states_after = len(states)

    # TODO #2568: some kind of a timeout is required here to wait for the learning to end
    return

    # `some_ursula_in_the_fleet` learned about `lonely_learner`
    assert states_before + 1 == states_after

    # The current fleet state of the Teacher...
    teacher_fleet_state_checksum = some_ursula_in_the_fleet.known_nodes.checksum

    # ...is the same as the learner, because both have learned about everybody at this point.
    assert teacher_fleet_state_checksum == states[-1].checksum
