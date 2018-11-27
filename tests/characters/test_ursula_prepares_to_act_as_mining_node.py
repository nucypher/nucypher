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
import os

import pytest

from nucypher.utilities.sandbox.middleware import MockRestMiddleware
from nucypher.utilities.sandbox.ursula import make_federated_ursulas


@pytest.mark.skip("To be implemented...?")
def test_federated_ursula_substantiates_stamp():
    assert False


def test_new_federated_ursula_announces_herself(ursula_federated_test_config):
    ursula_in_a_house, ursula_with_a_mouse = make_federated_ursulas(ursula_config=ursula_federated_test_config,
                                                                    quantity=2,
                                                                    know_each_other=False,
                                                                    network_middleware=MockRestMiddleware())

    # Neither Ursula knows about the other.
    assert ursula_in_a_house.known_nodes == ursula_with_a_mouse.known_nodes

    ursula_in_a_house.remember_node(ursula_with_a_mouse)

    # OK, now, ursula_in_a_house knows about ursula_with_a_mouse, but not vice-versa.
    assert ursula_with_a_mouse in ursula_in_a_house.known_nodes
    assert ursula_in_a_house not in ursula_with_a_mouse.known_nodes

    # But as ursula_in_a_house learns, she'll announce herself to ursula_with_a_mouse.
    ursula_in_a_house.learn_from_teacher_node()

    assert ursula_with_a_mouse in ursula_in_a_house.known_nodes
    assert ursula_in_a_house in ursula_with_a_mouse.known_nodes
