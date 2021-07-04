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

from nucypher.characters.lawful import Enrico
from nucypher.crypto.utils import keccak_digest
from nucypher.policy.orders import Revocation


def test_federated_grant(federated_alice, federated_bob, federated_ursulas):
    # Setup the policy details
    m, n = 2, 3
    policy_end_datetime = maya.now() + datetime.timedelta(days=5)
    label = b"this_is_the_path_to_which_access_is_being_granted"

    # Create the Policy, granting access to Bob
    policy = federated_alice.grant(federated_bob, label, m=m, n=n, expiration=policy_end_datetime)

    # Check the policy ID
    policy_id = keccak_digest(policy.label + bytes(federated_bob.stamp))
    assert policy_id == policy.id

    # Check Alice's active policies
    assert policy_id in federated_alice.active_policies
    assert federated_alice.active_policies[policy_id] == policy

    # The number of actually enacted arrangements is exactly equal to n.
    assert len(policy.treasure_map.destinations) == n

    # Let's look at the enacted arrangements.
    for ursula in federated_ursulas:
        if ursula.checksum_address in policy.treasure_map.destinations:
            assert ursula.checksum_address in policy.treasure_map.destinations


def test_federated_alice_can_decrypt(federated_alice, federated_bob):
    """
    Test that alice can decrypt data encrypted by an enrico
    for her own derived policy pubkey.
    """

    # Setup the policy details
    m, n = 2, 3
    policy_end_datetime = maya.now() + datetime.timedelta(days=5)
    label = b"this_is_the_path_to_which_access_is_being_granted"

    policy = federated_alice.create_policy(
        bob=federated_bob,
        label=label,
        m=m,
        n=n,
        expiration=policy_end_datetime,
    )

    enrico = Enrico.from_alice(
        federated_alice,
        policy.label,
    )
    plaintext = b"this is the first thing i'm encrypting ever."

    # use the enrico to encrypt the message
    message_kit, signature = enrico.encrypt_message(plaintext)

    # decrypt the data
    decrypted_data = federated_alice.verify_from(
        enrico,
        message_kit,
        signature=signature,
        decrypt=True,
        label=policy.label
    )

    assert plaintext == decrypted_data


@pytest.mark.skip("Needs rework post-TMcKF")  # TODO
@pytest.mark.usefixtures('federated_ursulas')
def test_revocation(federated_alice, federated_bob):
    m, n = 2, 3
    policy_end_datetime = maya.now() + datetime.timedelta(days=5)
    label = b"revocation test"

    policy = federated_alice.grant(federated_bob, label, m=m, n=n, expiration=policy_end_datetime)

    for node_id, encrypted_kfrag in policy.treasure_map:
        assert policy.revocation_kit[node_id]

    # Test revocation kit's signatures
    for revocation in policy.revocation_kit:
        assert revocation.verify_signature(federated_alice.stamp.as_umbral_pubkey())

    # Test Revocation deserialization
    revocation = policy.revocation_kit[node_id]
    revocation_bytes = bytes(revocation)
    deserialized_revocation = Revocation.from_bytes(revocation_bytes)
    assert deserialized_revocation == revocation

    # Attempt to revoke the new policy
    receipt, failed_revocations = federated_alice.revoke(policy)
    assert len(failed_revocations) == 0

    # Try to revoke the already revoked policy
    receipt, already_revoked = federated_alice.revoke(policy)
    assert len(already_revoked) == 3
