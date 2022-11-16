


import pytest

from nucypher_core import HRAC

from nucypher.characters.lawful import Ursula
from nucypher.crypto.utils import keccak_digest


def test_alice_creates_policy_with_correct_hrac(federated_alice, federated_bob, idle_federated_policy):
    """
    Alice creates a Policy.  It has the proper HRAC, unique per her, Bob, and the label
    """
    # TODO: what are we actually testing here?
    assert idle_federated_policy.hrac == HRAC(federated_alice.stamp.as_umbral_pubkey(),
                                              federated_bob.stamp.as_umbral_pubkey(),
                                              idle_federated_policy.label)


def test_alice_does_not_update_with_old_ursula_info(federated_alice, federated_ursulas):
    ursula = list(federated_ursulas)[0]
    old_metadata = bytes(ursula.metadata())

    # Alice has remembered Ursula.
    assert federated_alice.known_nodes[ursula.checksum_address] == ursula

    # But now, Ursula wants to sign and date her metadata again.  This causes a new timestamp.
    ursula._metadata = None
    ursula.metadata()

    # Indeed, her metadata is not the same now.
    assert bytes(ursula.metadata()) != old_metadata

    old_ursula = Ursula.from_metadata_bytes(old_metadata)

    # Once Alice learns about Ursula's updated info...
    federated_alice.remember_node(ursula)

    # ...she can't learn about old ursula anymore.
    federated_alice.remember_node(old_ursula)

    new_metadata = bytes(federated_alice.known_nodes[ursula.checksum_address].metadata())
    assert new_metadata != old_metadata
