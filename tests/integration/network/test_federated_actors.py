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

import pytest

from nucypher.crypto.api import keccak_digest
from tests.utils.middleware import MockRestMiddleware


def test_alice_creates_policy_with_correct_hrac(idle_federated_policy):
    """
    Alice creates a Policy.  It has the proper HRAC, unique per her, Bob, and the label
    """
    alice = idle_federated_policy.alice
    bob = idle_federated_policy.bob

    assert idle_federated_policy.hrac() == keccak_digest(bytes(alice.stamp)
                                                         + bytes(bob.stamp)
                                                         + idle_federated_policy.label)


def test_alice_sets_treasure_map(enacted_federated_policy, federated_ursulas):
    """
    Having enacted all the policies of a PolicyGroup, Alice creates a TreasureMap and ...... TODO
    """
    enacted_federated_policy.publish_treasure_map(network_middleware=MockRestMiddleware())
    treasure_map_index = bytes.fromhex(enacted_federated_policy.treasure_map.public_id())
    found = 0
    for node in enacted_federated_policy.bob.matching_nodes_among(enacted_federated_policy.alice.known_nodes):
        treasure_map_as_set_on_network = node.treasure_maps[treasure_map_index]
        assert treasure_map_as_set_on_network == enacted_federated_policy.treasure_map
        found += 1
    assert found


def test_treasure_map_stored_by_ursula_is_the_correct_one_for_bob(federated_alice,
                                                                  federated_bob,
                                                                  federated_ursulas,
                                                                  enacted_federated_policy):
    """
    The TreasureMap given by Alice to Ursula is the correct one for Bob; he can decrypt and read it.
    """

    treasure_map_index = bytes.fromhex(enacted_federated_policy.treasure_map.public_id())
    treasure_map_as_set_on_network = list(federated_ursulas)[0].treasure_maps[treasure_map_index]

    hrac_by_bob = federated_bob.construct_policy_hrac(federated_alice.stamp, enacted_federated_policy.label)
    assert enacted_federated_policy.hrac() == hrac_by_bob

    hrac, map_id_by_bob = federated_bob.construct_hrac_and_map_id(federated_alice.stamp, enacted_federated_policy.label)
    assert map_id_by_bob == treasure_map_as_set_on_network.public_id()


def test_bob_can_retreive_the_treasure_map_and_decrypt_it(enacted_federated_policy, federated_ursulas):
    """
    Above, we showed that the TreasureMap saved on the network is the correct one for Bob.  Here, we show
    that Bob can retrieve it with only the information about which he is privy pursuant to the PolicyGroup.
    """
    bob = enacted_federated_policy.bob

    # Of course, in the real world, Bob has sufficient information to reconstitute a PolicyGroup, gleaned, we presume,
    # through a side-channel with Alice.

    # If Bob doesn't know about any Ursulas, he can't find the TreasureMap via the REST swarm:
    with pytest.raises(bob.NotEnoughNodes):
        treasure_map_from_wire = bob.get_treasure_map(enacted_federated_policy.alice.stamp,
                                                      enacted_federated_policy.label)

    # Bob finds out about one Ursula (in the real world, a seed node)
    bob.remember_node(list(federated_ursulas)[0])

    # ...and then learns about the rest of the network.
    bob.learn_from_teacher_node(eager=True)

    # Now he'll have better success finding that map.
    treasure_map_from_wire = bob.get_treasure_map(enacted_federated_policy.alice.stamp,
                                                  enacted_federated_policy.label)

    assert enacted_federated_policy.treasure_map == treasure_map_from_wire


def test_treasure_map_is_legit(enacted_federated_policy):
    """
    Sure, the TreasureMap can get to Bob, but we also need to know that each Ursula in the TreasureMap is on the network.
    """
    for ursula_address, _node_id in enacted_federated_policy.treasure_map:
        assert ursula_address in enacted_federated_policy.bob.known_nodes.addresses()
