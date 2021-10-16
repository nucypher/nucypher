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

from nucypher.core import MessageKit, RevocationOrder

from nucypher.characters.lawful import Enrico
from nucypher.crypto.utils import keccak_digest


def test_federated_grant(federated_alice, federated_bob, federated_ursulas):
    # Setup the policy details
    threshold, shares = 2, 3
    policy_end_datetime = maya.now() + datetime.timedelta(days=5)
    label = b"this_is_the_path_to_which_access_is_being_granted"

    # Create the Policy, granting access to Bob
    policy = federated_alice.grant(federated_bob, label, threshold=threshold, shares=shares, expiration=policy_end_datetime)

    # Check Alice's active policies
    assert policy.hrac in federated_alice.active_policies
    assert federated_alice.active_policies[policy.hrac] == policy

    treasure_map = federated_bob._decrypt_treasure_map(policy.treasure_map,
                                                       policy.publisher_verifying_key)

    # The number of actually enacted arrangements is exactly equal to shares.
    assert len(treasure_map.destinations) == shares

    # Let's look at the enacted arrangements.
    for ursula in federated_ursulas:
        if ursula.checksum_address in treasure_map.destinations:
            kfrag_kit = treasure_map.destinations[ursula.checksum_address]

            # TODO: try to decrypt?
            # TODO: Use a new type for EncryptedKFrags?
            assert isinstance(kfrag_kit, MessageKit)


def test_federated_alice_can_decrypt(federated_alice, federated_bob):
    """
    Test that alice can decrypt data encrypted by an enrico
    for her own derived policy pubkey.
    """

    # Setup the policy details
    threshold, shares = 2, 3
    policy_end_datetime = maya.now() + datetime.timedelta(days=5)
    label = b"this_is_the_path_to_which_access_is_being_granted"

    policy = federated_alice.create_policy(
        bob=federated_bob,
        label=label,
        threshold=threshold,
        shares=shares,
        expiration=policy_end_datetime,
    )

    enrico = Enrico.from_alice(
        federated_alice,
        policy.label,
    )
    plaintext = b"this is the first thing i'm encrypting ever."

    # use the enrico to encrypt the message
    message_kit = enrico.encrypt_message(plaintext)

    # decrypt the data
    decrypted_data = federated_alice.decrypt_message_kit(
        label=policy.label,
        message_kit=message_kit,
    )

    assert [plaintext] == decrypted_data


@pytest.mark.skip("Needs rework post-TMcKF")  # TODO
@pytest.mark.usefixtures('federated_ursulas')
def test_revocation(federated_alice, federated_bob):
    threshold, shares = 2, 3
    policy_end_datetime = maya.now() + datetime.timedelta(days=5)
    label = b"revocation test"

    policy = federated_alice.grant(federated_bob, label, threshold=threshold, shares=shares, expiration=policy_end_datetime)

    for node_id, encrypted_kfrag in policy.treasure_map:
        assert policy.revocation_kit[node_id]

    # Test revocation kit's signatures
    for revocation in policy.revocation_kit:
        assert revocation.verify_signature(federated_alice.stamp.as_umbral_pubkey())

    # Test Revocation deserialization
    revocation = policy.revocation_kit[node_id]
    revocation_bytes = bytes(revocation)
    deserialized_revocation = RevocationOrder.from_bytes(revocation_bytes)
    assert deserialized_revocation == revocation

    # Attempt to revoke the new policy
    receipt, failed_revocations = federated_alice.revoke(policy)
    assert len(failed_revocations) == 0

    # Try to revoke the already revoked policy
    receipt, already_revoked = federated_alice.revoke(policy)
    assert len(already_revoked) == 3
