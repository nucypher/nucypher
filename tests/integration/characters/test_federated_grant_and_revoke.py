


import datetime

import maya
import pytest
from nucypher_core import EncryptedKeyFrag, RevocationOrder

from nucypher.characters.lawful import Enrico


def test_grant(blockchain_alice, blockchain_bob, blockchain_ursulas):
    # Setup the policy details
    threshold, shares = 2, 3
    policy_end_datetime = maya.now() + datetime.timedelta(days=5)
    label = b"this_is_the_path_to_which_access_is_being_granted"

    # Create the Policy, granting access to Bob
    policy = blockchain_alice.grant(
        blockchain_bob,
        label,
        threshold=threshold,
        shares=shares,
        expiration=policy_end_datetime,
    )

    # Check Alice's active policies
    assert policy.hrac in blockchain_alice.active_policies
    assert blockchain_alice.active_policies[policy.hrac] == policy

    treasure_map = blockchain_bob._decrypt_treasure_map(
        policy.treasure_map, policy.publisher_verifying_key
    )

    # The number of map destinations is exactly equal to shares.
    assert len(treasure_map.destinations) == shares

    # Let's look at the destinations.
    for ursula in blockchain_ursulas:
        if ursula.canonical_address in treasure_map.destinations:
            kfrag_kit = treasure_map.destinations[ursula.canonical_address]

            # TODO: Deeper testing here: try to decrypt?
            # TODO: Use a new type for EncryptedKFrags?
            assert isinstance(kfrag_kit, EncryptedKeyFrag)


def test_blockchain_alice_can_decrypt(blockchain_alice, blockchain_bob):
    """
    Test that alice can decrypt data encrypted by an enrico
    for her own derived policy pubkey.
    """

    # Setup the policy details
    threshold, shares = 2, 3
    policy_end_datetime = maya.now() + datetime.timedelta(days=5)
    label = b"this_is_the_path_to_which_access_is_being_granted"

    policy = blockchain_alice.create_policy(
        bob=blockchain_bob,
        label=label,
        threshold=threshold,
        shares=shares,
        expiration=policy_end_datetime,
    )

    enrico = Enrico.from_alice(
        blockchain_alice,
        policy.label,
    )
    plaintext = b"this is the first thing i'm encrypting ever."

    # use the enrico to encrypt the message
    message_kit = enrico.encrypt_message(plaintext)

    # decrypt the data
    decrypted_data = blockchain_alice.decrypt_message_kit(
        label=policy.label,
        message_kit=message_kit,
    )

    assert [plaintext] == decrypted_data


@pytest.mark.skip("Needs rework post-TMcKF")  # TODO: Implement offchain revocation.
@pytest.mark.usefixtures("blockchain_ursulas")
def test_revocation(blockchain_alice, blockchain_bob):
    threshold, shares = 2, 3
    policy_end_datetime = maya.now() + datetime.timedelta(days=5)
    label = b"revocation test"

    policy = blockchain_alice.grant(
        blockchain_bob,
        label,
        threshold=threshold,
        shares=shares,
        expiration=policy_end_datetime,
    )

    for node_id, encrypted_kfrag in policy.treasure_map:
        assert policy.revocation_kit[node_id]

    # Test revocation kit's signatures
    for revocation in policy.revocation_kit:
        assert revocation.verify_signature(blockchain_alice.stamp.as_umbral_pubkey())

    # Test Revocation deserialization
    revocation = policy.revocation_kit[node_id]
    revocation_bytes = bytes(revocation)
    deserialized_revocation = RevocationOrder.from_bytes(revocation_bytes)
    assert deserialized_revocation == revocation

    # Attempt to revoke the new policy
    receipt, failed_revocations = blockchain_alice.revoke(policy)
    assert len(failed_revocations) == 0

    # Try to revoke the already revoked policy
    receipt, already_revoked = blockchain_alice.revoke(policy)
    assert len(already_revoked) == 3
