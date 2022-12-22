from nucypher_core import HRAC

from nucypher.characters.lawful import Ursula


def test_alice_creates_policy_with_correct_hrac(alice, bob, idle_policy):
    """
    Alice creates a Policy.  It has the proper HRAC, unique per her, Bob, and the label
    """
    # TODO: what are we actually testing here?
    assert idle_policy.hrac == HRAC(
        alice.stamp.as_umbral_pubkey(), bob.stamp.as_umbral_pubkey(), idle_policy.label
    )


def test_alice_does_not_update_with_old_ursula_info(alice, ursulas):
    ursula = list(ursulas)[0]
    old_metadata = bytes(ursula.metadata())

    # Alice has remembered Ursula.
    assert alice.known_nodes[ursula.checksum_address] == ursula

    # But now, Ursula wants to sign and date her metadata again.  This causes a new timestamp.
    ursula._metadata = None
    ursula.metadata()

    # Indeed, her metadata is not the same now.
    assert bytes(ursula.metadata()) != old_metadata

    old_ursula = Ursula.from_metadata_bytes(old_metadata)

    # Once Alice learns about Ursula's updated info...
    alice.remember_node(ursula)

    # ...she can't learn about old ursula anymore.
    alice.remember_node(old_ursula)

    new_metadata = bytes(alice.known_nodes[ursula.checksum_address].metadata())
    assert new_metadata != old_metadata
