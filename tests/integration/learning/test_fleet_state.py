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

from constant_sorrow.constants import FLEET_STATES_MATCH, NO_KNOWN_NODES
from functools import partial
from hendrix.experience import crosstown_traffic
from hendrix.utils.test_utils import crosstownTaskListDecoratorFactory

from tests.utils.ursula import make_federated_ursulas


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


def test_old_state_is_preserved(federated_ursulas, lonely_ursula_maker):
    lonely_learner = lonely_ursula_maker().pop()

    # This Ursula doesn't know about any nodes.
    assert len(lonely_learner.known_nodes) == 0

    some_ursula_in_the_fleet = list(federated_ursulas)[0]
    lonely_learner.remember_node(some_ursula_in_the_fleet)
    checksum_after_learning_one = lonely_learner.known_nodes.checksum
    assert some_ursula_in_the_fleet in lonely_learner.known_nodes
    assert some_ursula_in_the_fleet.checksum_address in lonely_learner.known_nodes
    assert len(lonely_learner.known_nodes) == 1
    assert lonely_learner.known_nodes.population == 2

    another_ursula_in_the_fleet = list(federated_ursulas)[1]
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


def test_state_is_recorded_after_learning(federated_ursulas, lonely_ursula_maker):
    """
    Similar to above, but this time we show that the Learner records a new state only once after learning
    about a bunch of nodes.
    """
    _lonely_ursula_maker = partial(lonely_ursula_maker, quantity=1)
    lonely_learner = _lonely_ursula_maker().pop()
    states = lonely_learner.known_nodes._archived_states

    # This Ursula doesn't know about any nodes.
    assert len(lonely_learner.known_nodes) == 0

    some_ursula_in_the_fleet = list(federated_ursulas)[0]
    lonely_learner.remember_node(some_ursula_in_the_fleet)
    assert len(states) == 2  # Saved a fleet state when we remembered this node.

    # The first fleet state is just us and the one about whom we learned, which is part of the fleet.
    assert states[-1].population == 2

    # The rest of the fucking owl.
    lonely_learner.learn_from_teacher_node()

    # There are two new states: one created after seednodes are loaded, to select a teacher,
    # and the second after we get the rest of the nodes from the seednodes.
    assert len(states) == 4

    # When we ran learn_from_teacher_node, we also loaded the rest of the fleet.
    assert states[-1].population == len(federated_ursulas) + 1


def test_teacher_records_new_fleet_state_upon_hearing_about_new_node(federated_ursulas, lonely_ursula_maker):
    _lonely_ursula_maker = partial(lonely_ursula_maker, quantity=1)
    lonely_learner = _lonely_ursula_maker().pop()

    some_ursula_in_the_fleet = list(federated_ursulas)[0]

    lonely_learner.remember_node(some_ursula_in_the_fleet)

    states = some_ursula_in_the_fleet.known_nodes._archived_states

    states_before = len(states)
    lonely_learner.learn_from_teacher_node()
    states_after = len(states)

    # FIXME: some kind of a timeout is required here to wait for the learning to end
    return

    # `some_ursula_in_the_fleet` learned about `lonely_learner`
    assert states_before + 1 == states_after

    # The current fleet state of the Teacher...
    teacher_fleet_state_checksum = some_ursula_in_the_fleet.fleet_state_checksum

    # ...is the same as the learner, because both have learned about everybody at this point.
    assert teacher_fleet_state_checksum == states[-1].checksum
