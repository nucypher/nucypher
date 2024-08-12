import datetime

import maya
from nucypher_core import EncryptedKeyFrag

from nucypher.characters.lawful import Enrico


def test_grant(alice, bob, ursulas):
    # Setup the policy details
    threshold, shares = 2, 3
    policy_end_datetime = maya.now() + datetime.timedelta(days=5)
    label = b"this_is_the_path_to_which_access_is_being_granted"

    # Create the Policy, granting access to Bob
    policy = alice.grant(
        bob, label, threshold=threshold, shares=shares, expiration=policy_end_datetime
    )

    # Check Alice's active policies
    assert policy.hrac in alice.active_policies
    assert alice.active_policies[policy.hrac] == policy

    treasure_map = bob._decrypt_treasure_map(
        policy.treasure_map, policy.publisher_verifying_key
    )

    # The number of map destinations is exactly equal to shares.
    assert len(treasure_map.destinations) == shares

    # Let's look at the destinations.
    for ursula in ursulas:
        if ursula.canonical_address in treasure_map.destinations:
            kfrag_kit = treasure_map.destinations[ursula.canonical_address]

            # TODO: Deeper testing here: try to decrypt?
            # TODO: Use a new type for EncryptedKFrags?
            assert isinstance(kfrag_kit, EncryptedKeyFrag)


def test_alice_can_decrypt(alice, bob):
    """
    Test that alice can decrypt data encrypted by an enrico
    for her own derived policy pubkey.
    """

    # Setup the policy details
    threshold, shares = 2, 3
    policy_end_datetime = maya.now() + datetime.timedelta(days=5)
    label = b"this_is_the_path_to_which_access_is_being_granted"

    policy = alice.create_policy(
        bob=bob,
        label=label,
        threshold=threshold,
        shares=shares,
        expiration=policy_end_datetime,
    )

    enrico = Enrico.from_alice(
        alice,
        policy.label,
    )
    plaintext = b"this is the first thing i'm encrypting ever."

    # use the enrico to encrypt the message
    message_kit = enrico.encrypt_for_pre(plaintext)

    # decrypt the data
    decrypted_data = alice.decrypt_message_kit(
        label=policy.label,
        message_kit=message_kit,
    )

    assert [plaintext] == decrypted_data
