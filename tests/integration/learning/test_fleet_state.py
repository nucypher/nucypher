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

    another_ursula_in_the_fleet = list(federated_ursulas)[1]
    lonely_learner.remember_node(another_ursula_in_the_fleet)
    checksum_after_learning_two = lonely_learner.known_nodes.checksum

    assert checksum_after_learning_one != checksum_after_learning_two

    proper_first_state = sorted([some_ursula_in_the_fleet, lonely_learner], key=lambda n: n.checksum_address)
    assert lonely_learner.known_nodes.states[checksum_after_learning_one].nodes == proper_first_state

    proper_second_state = sorted([some_ursula_in_the_fleet, another_ursula_in_the_fleet, lonely_learner],
                                 key=lambda n: n.checksum_address)
    assert lonely_learner.known_nodes.states[checksum_after_learning_two].nodes == proper_second_state


def test_state_is_recorded_after_learning(federated_ursulas, lonely_ursula_maker):
    """
    Similar to above, but this time we show that the Learner records a new state only once after learning
    about a bunch of nodes.
    """
    _lonely_ursula_maker = partial(lonely_ursula_maker, quantity=1)
    lonely_learner = _lonely_ursula_maker().pop()

    # This Ursula doesn't know about any nodes.
    assert len(lonely_learner.known_nodes) == 0

    some_ursula_in_the_fleet = list(federated_ursulas)[0]
    lonely_learner.remember_node(some_ursula_in_the_fleet)
    assert len(lonely_learner.known_nodes.states) == 1  # Saved a fleet state when we remembered this node.

    # The rest of the fucking owl.
    lonely_learner.learn_from_teacher_node()

    states = list(lonely_learner.known_nodes.states.values())
    assert len(states) == 2

    assert len(states[0].nodes) == 2  # The first fleet state is just us and the one about whom we learned, which is part of the fleet.
    assert len(states[1].nodes) == len(federated_ursulas) + 1  # When we ran learn_from_teacher_node, we also loaded the rest of the fleet.
