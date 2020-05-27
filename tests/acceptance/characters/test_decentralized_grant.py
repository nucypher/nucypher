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
from nucypher.policy.collections import PolicyCredential


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
        retrieved_policy = arrangement.ursula.datastore.get_policy_arrangement(arrangement.id.hex().encode())
        retrieved_kfrag = KFrag.from_bytes(retrieved_policy.kfrag)

        assert kfrag == retrieved_kfrag

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
