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

import datetime
import maya
import pytest

from nucypher.crypto.utils import keccak_digest
from nucypher.datastore.models import PolicyArrangement
from nucypher.datastore.models import TreasureMap as DatastoreTreasureMap
from nucypher.policy.collections import SignedTreasureMap as DecentralizedTreasureMap


def test_decentralized_grant(blockchain_alice, blockchain_bob, blockchain_ursulas):
    # Setup the policy details
    n = 3
    policy_end_datetime = maya.now() + datetime.timedelta(days=35)
    label = b"this_is_the_path_to_which_access_is_being_granted"

    # Create the Policy, Granting access to Bob
    policy = blockchain_alice.grant(bob=blockchain_bob,
                                    label=label,
                                    m=2,
                                    n=n,
                                    rate=int(1e18),  # one ether
                                    expiration=policy_end_datetime)

    # Check the policy ID
    policy_id = keccak_digest(label + bytes(blockchain_bob.stamp))
    assert policy_id == policy.id

    # The number of actually enacted arrangements is exactly equal to n.
    assert len(policy.treasure_map.destinations) == n

    # Let's look at the enacted arrangements.
    for ursula in blockchain_ursulas:
        if ursula.checksum_address in policy.treasure_map.destinations:
            arrangement_id = policy.treasure_map.destinations[ursula.checksum_address]

            # Get the Arrangement from Ursula's datastore, looking up by the Arrangement ID.
            with ursula.datastore.describe(PolicyArrangement, arrangement_id.hex()) as policy_arrangement:
                retrieved_kfrag = policy_arrangement.kfrag
            assert bool(retrieved_kfrag) # TODO: try to assemble them back?


def test_alice_sets_treasure_map_decentralized(enacted_blockchain_policy, blockchain_alice, blockchain_bob, blockchain_ursulas):
    """
    Same as test_alice_sets_treasure_map except with a blockchain policy.
    """
    treasure_map_hrac = enacted_blockchain_policy.treasure_map._hrac[:16].hex()
    found = 0
    for node in blockchain_bob.matching_nodes_among(blockchain_alice.known_nodes):
        with node.datastore.describe(DatastoreTreasureMap, treasure_map_hrac) as treasure_map_on_node:
            assert DecentralizedTreasureMap.from_bytes(treasure_map_on_node.treasure_map) == enacted_blockchain_policy.treasure_map
        found += 1
    assert found


def test_bob_retrieves_treasure_map_from_decentralized_node(enacted_blockchain_policy, blockchain_alice, blockchain_bob):
    """
    This is the same test as `test_bob_retrieves_the_treasure_map_and_decrypt_it`,
    except with an `enacted_blockchain_policy`.
    """
    bob = blockchain_bob
    _previous_domain = bob.domain
    bob.domain = None  # Bob has no knowledge of the network.

    with pytest.raises(bob.NotEnoughTeachers):
        treasure_map_from_wire = bob.get_treasure_map(blockchain_alice.stamp,
                                                      enacted_blockchain_policy.label)

    # Bob finds out about one Ursula (in the real world, a seed node, hardcoded based on his learning domain)
    bob.done_seeding = False
    bob.domain = _previous_domain

    # ...and then learns about the rest of the network.
    bob.learn_from_teacher_node(eager=True)

    # Now he'll have better success finding that map.
    treasure_map_from_wire = bob.get_treasure_map(blockchain_alice.stamp,
                                                  enacted_blockchain_policy.label)
    assert enacted_blockchain_policy.treasure_map == treasure_map_from_wire
