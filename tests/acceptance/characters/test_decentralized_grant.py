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
from umbral.kfrags import KFrag

from nucypher.crypto.api import keccak_digest
from nucypher.datastore.models import PolicyArrangement, TreasureMap as DatastoreTreasureMap
from nucypher.policy.collections import PolicyCredential, SignedTreasureMap as DecentralizedTreasureMap
from tests.utils.middleware import MockRestMiddleware


@pytest.mark.usefixtures('blockchain_ursulas')
def test_decentralized_grant(blockchain_alice, blockchain_bob, agency):
    # Setup the policy details
    n = 3
    policy_end_datetime = maya.now() + datetime.timedelta(days=5)
    label = b"this_is_the_path_to_which_access_is_being_granted"

    # Create the Policy, Granting access to Bob
    policy = blockchain_alice.grant(bob=blockchain_bob,
                                    label=label,
                                    m=2,
                                    n=n,
                                    rate=int(1e18),  # one ether
                                    expiration=policy_end_datetime)

    # Check the policy ID
    policy_id = keccak_digest(policy.label + bytes(policy.bob.stamp))
    assert policy_id == policy.id

    # The number of accepted arrangements at least the number of Ursulas we're using (n)
    assert len(policy._accepted_arrangements) >= n

    # The number of actually enacted arrangements is exactly equal to n.
    assert len(policy._enacted_arrangements) == n

    # Let's look at the enacted arrangements.
    for kfrag in policy.kfrags:
        arrangement = policy._enacted_arrangements[kfrag]

        # Get the Arrangement from Ursula's datastore, looking up by the Arrangement ID.
        with arrangement.ursula.datastore.describe(PolicyArrangement, arrangement.id.hex()) as policy_arrangement:
            assert kfrag == policy_arrangement.kfrag

    # Test PolicyCredential w/o TreasureMap
    credential = policy.credential(with_treasure_map=False)
    assert credential.alice_verifying_key == policy.alice.stamp
    assert credential.label == policy.label
    assert credential.expiration == policy.expiration
    assert credential.policy_pubkey == policy.public_key
    assert credential.treasure_map is None

    cred_json = credential.to_json()
    deserialized_cred = PolicyCredential.from_json(cred_json)
    assert credential == deserialized_cred

    # Test PolicyCredential w/ TreasureMap
    credential = policy.credential()
    assert credential.alice_verifying_key == policy.alice.stamp
    assert credential.label == policy.label
    assert credential.expiration == policy.expiration
    assert credential.policy_pubkey == policy.public_key
    assert credential.treasure_map == policy.treasure_map

    cred_json = credential.to_json()
    deserialized_cred = PolicyCredential.from_json(cred_json)
    assert credential == deserialized_cred


def test_alice_sets_treasure_map_decentralized(enacted_blockchain_policy):
    """
    Same as test_alice_sets_treasure_map except with a blockchain policy.
    """
    enacted_blockchain_policy.publish_treasure_map(network_middleware=MockRestMiddleware())
    treasure_map_hrac = enacted_blockchain_policy.treasure_map._hrac[:16].hex()
    found = 0
    for node in enacted_blockchain_policy.bob.matching_nodes_among(enacted_blockchain_policy.alice.known_nodes):
        with node.datastore.describe(DatastoreTreasureMap, treasure_map_hrac) as treasure_map_on_node:
            assert DecentralizedTreasureMap.from_bytes(treasure_map_on_node.treasure_map) == enacted_blockchain_policy.treasure_map
        found += 1
    assert found


def test_bob_retrieves_treasure_map_from_decentralized_node(enacted_blockchain_policy):
    """
    This is the same test as `test_bob_retrieves_the_treasure_map_and_decrypt_it`,
    except with an `enacted_blockchain_policy`.
    """
    bob = enacted_blockchain_policy.bob
    _previous_domain = bob.domain
    bob.domain = None  # Bob has no knowledge of the network.

    with pytest.raises(bob.NotEnoughTeachers):
        treasure_map_from_wire = bob.get_treasure_map(enacted_blockchain_policy.alice.stamp,
                                                      enacted_blockchain_policy.label)

    # Bob finds out about one Ursula (in the real world, a seed node, hardcoded based on his learning domain)
    bob.done_seeding = False
    bob.domain = _previous_domain

    # ...and then learns about the rest of the network.
    bob.learn_from_teacher_node(eager=True)

    # Now he'll have better success finding that map.
    treasure_map_from_wire = bob.get_treasure_map(enacted_blockchain_policy.alice.stamp,
                                                  enacted_blockchain_policy.label)
    assert enacted_blockchain_policy.treasure_map == treasure_map_from_wire
