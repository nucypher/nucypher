import datetime
import maya
import pytest
from eth_account._utils.signing import to_standard_signature_bytes

from nucypher.characters.lawful import Enrico, Ursula
from nucypher.characters.unlawful import Vladimir
from nucypher.crypto.utils import verify_eip_191
from nucypher.policy.policies import Policy
from tests.constants import MOCK_ETH_PROVIDER_URI, TEST_ETH_PROVIDER_URI
from tests.utils.middleware import NodeIsDownMiddleware


def test_stakers_bond_to_ursulas(ursulas, test_registry, staking_providers):
    assert len(ursulas) == len(staking_providers)
    for ursula in ursulas:
        ursula.validate_operator(
            registry=test_registry, eth_endpoint=TEST_ETH_PROVIDER_URI
        )
        assert ursula.verified_operator


def test_ursula_substantiates_stamp(ursulas):
    first_ursula = list(ursulas)[0]
    signature_as_bytes = first_ursula.operator_signature
    signature_as_bytes = to_standard_signature_bytes(signature_as_bytes)
    # `operator_address` was derived in nucypher_core, check it independently
    assert verify_eip_191(address=first_ursula.operator_address,
                          message=bytes(first_ursula.stamp),
                          signature=signature_as_bytes)


def test_blockchain_ursula_verifies_stamp(ursulas):
    first_ursula = list(ursulas)[0]

    # This Ursula does not yet have a verified stamp
    first_ursula.verified_stamp = False
    first_ursula.validate_operator()

    # ...but now it's verified.
    assert first_ursula.verified_stamp


def remote_vladimir(**kwds):
    vladimir = Vladimir.from_target_ursula(**kwds)
    remote_vladimir = Ursula.from_metadata_bytes(bytes(vladimir.metadata())).mature()
    return remote_vladimir


def test_vladimir_cannot_verify_interface_with_ursulas_signing_key(
    testerchain, ursulas
):
    his_target = list(ursulas)[4]

    # Vladimir has his own ether address; he hopes to publish it along with Ursula's details
    # so that Alice (or whomever) pays him instead of Ursula, even though Ursula is providing the service.

    # He finds a target and verifies that its interface is valid.
    assert his_target.validate_metadata_signature()

    # Now Vladimir imitates Ursula - copying her public keys and interface info, but inserting his ether address.
    vladimir = remote_vladimir(target_ursula=his_target)

    # Now, even though his public signing key matches Ursulas...
    assert vladimir.metadata().payload.verifying_key == his_target.stamp.as_umbral_pubkey()

    # ...he is unable to pretend that his interface is valid
    # because the validity check contains the canonical public address as part of its message.
    with pytest.raises(vladimir.InvalidNode, match="Metadata signature is invalid"):
        vladimir.validate_metadata_signature()

    # Consequently, the metadata as a whole is also invalid.
    with pytest.raises(vladimir.InvalidNode, match="Metadata signature is invalid"):
        vladimir.validate_metadata()


def test_vladimir_uses_his_own_signing_key(alice, ursulas, test_registry):
    """
    Similar to the attack above, but this time Vladimir makes his own interface signature
    using his own signing key, which he claims is Ursula's.
    """
    his_target = list(ursulas)[4]
    vladimir = remote_vladimir(target_ursula=his_target,
                               sign_metadata=True)

    # The metadata signature does not match the verifying key
    with pytest.raises(vladimir.InvalidNode, match="Metadata signature is invalid"):
        vladimir.validate_metadata_signature()

    # Let's try again, but this time put our own key in the metadata, too
    vladimir = remote_vladimir(target_ursula=his_target,
                               substitute_verifying_key=True,
                               sign_metadata=True)

    # With this slightly more sophisticated attack, his metadata does appear valid.
    # In fact, we pass the decentralized evidence verification too,
    # since the worker address is derived from it - so it is valid automatically.
    vladimir.validate_metadata()

    # But since the derived worker address is bogus, the staker-worker bond check fails.
    vladimir = remote_vladimir(target_ursula=his_target,
                               substitute_verifying_key=True,
                               sign_metadata=True)

    message = f"Operator {vladimir.operator_address} is not bonded"
    with pytest.raises(vladimir.UnbondedOperator, match=message):
        vladimir.validate_metadata(
            registry=test_registry, eth_endpoint=TEST_ETH_PROVIDER_URI
        )


def test_vladimir_invalidity_without_stake(testerchain, ursulas, alice):
    his_target = list(ursulas)[4]

    vladimir = remote_vladimir(target_ursula=his_target,
                               substitute_verifying_key=True,
                               sign_metadata=True)

    # All the signature validations will pass (without the registry check)
    vladimir.validate_metadata()

    # But the actual handshake proves him wrong.
    message = "Wallet address swapped out.  It appears that someone is trying to defraud this node."
    with pytest.raises(vladimir.InvalidNode, match=message):
        vladimir.verify_node(alice.network_middleware.client)


# TODO: Change name of this file, extract this test
def test_ursulas_reencrypt(ursulas, alice, bob, policy_value):
    label = b'bbo'

    # TODO: Make sample selection buffer configurable - #1061
    threshold = shares = 10
    expiration = maya.now() + datetime.timedelta(days=35)

    _policy = alice.grant(
        bob=bob,
        label=label,
        threshold=threshold,
        shares=shares,
        expiration=expiration,
        value=policy_value,
    )

    enrico = Enrico.from_alice(alice, label)

    message = b"Oh, this isn't even BO. This is beyond BO. It's BBO."

    message_kit = enrico.encrypt_for_pre(message)

    bob.start_learning_loop(now=True)

    plaintexts = bob.retrieve_and_decrypt(
        [message_kit],
        encrypted_treasure_map=_policy.treasure_map,
        alice_verifying_key=alice.stamp.as_umbral_pubkey(),
    )
    assert plaintexts == [message]

    # Let's consider also that a node may be down when granting
    alice.network_middleware = NodeIsDownMiddleware(eth_endpoint=MOCK_ETH_PROVIDER_URI)
    alice.network_middleware.node_is_down(ursulas[0])

    with pytest.raises(Policy.NotEnoughUrsulas):
        _policy = alice.grant(
            bob=bob,
            label=b"another-label",
            threshold=threshold,
            shares=shares,
            expiration=expiration,
            value=policy_value,
        )
