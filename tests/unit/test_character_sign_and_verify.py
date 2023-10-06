import pytest

from nucypher.characters.lawful import Alice, Character
from nucypher.config.constants import TEMPORARY_DOMAIN
from nucypher.crypto.powers import CryptoPower, NoSigningPower, SigningPower
from nucypher.crypto.signing import InvalidSignature
from nucypher.policy.payment import FreeReencryptions
from tests.constants import MOCK_ETH_PROVIDER_URI

"""
Chapter 1: SIGNING
"""


def test_actor_without_signing_power_cannot_sign():
    """
    We can create a Character with no real CryptoPower to speak of.
    This Character can't even sign a message.
    """
    cannot_sign = CryptoPower(power_ups=[])
    non_signer = Character(
        crypto_power=cannot_sign,
        start_learning_now=False,
        domain=TEMPORARY_DOMAIN,
        eth_endpoint=MOCK_ETH_PROVIDER_URI,
    )

    # The non-signer's stamp doesn't work for signing...
    with pytest.raises(NoSigningPower):
        non_signer.stamp("something")

    # ...or as a way to cast the (non-existent) public key to bytes.
    with pytest.raises(NoSigningPower):
        bytes(non_signer.stamp)


def test_actor_with_signing_power_can_sign():
    """
    However, simply giving that character a PowerUp bestows the power to sign.

    Instead of having a Character verify the signature, we'll use the lower level API.
    """
    message = b"Llamas."

    signer = Character(
        crypto_power_ups=[SigningPower],
        is_me=True,
        start_learning_now=False,
        domain=TEMPORARY_DOMAIN,
        eth_endpoint=MOCK_ETH_PROVIDER_URI,
    )
    stamp_of_the_signer = signer.stamp

    # We can use the signer's stamp to sign a message (since the signer is_me)...
    signature = stamp_of_the_signer(message)

    # ...or to get the signer's public key for verification purposes.
    # (note: we verify directly using Umbral API, skipping Character)
    verification = signature.verify(stamp_of_the_signer.as_umbral_pubkey(), message)

    assert verification is True


def test_anybody_can_verify(random_address):
    """
    In the last example, we used the lower-level Crypto API to verify the signature.

    Here, we show that anybody can do it without needing to directly access Crypto.
    """
    # Alice can sign by default, by dint of her _default_crypto_powerups.
    alice = Alice(
        start_learning_now=False,
        domain=TEMPORARY_DOMAIN,
        checksum_address=random_address,
        pre_payment_method=FreeReencryptions(),
        eth_endpoint=MOCK_ETH_PROVIDER_URI,
    )

    # So, our story is fairly simple: an everyman meets Alice.
    somebody = Character(
        start_learning_now=False,
        domain=TEMPORARY_DOMAIN,
        eth_endpoint=MOCK_ETH_PROVIDER_URI,
    )

    # Alice signs a message.
    message = b"A message for all my friends who can only verify and not sign. You know who you are."
    signature = alice.stamp(message)

    # Our everyman can verify it.
    somebody.verify_from(alice, message, signature)

    # Of course, verification fails with any fake message
    with pytest.raises(InvalidSignature):
        fake = b"McLovin      892 Momona St.  Honolulu, HI 96820"
        somebody.verify_from(alice, fake, signature)

    # Signature verification also works when Alice is not living with our
    # everyman in the same process, and he only knows her by her public key
    alice_pubkey_bytes = bytes(alice.stamp)
    hearsay_alice = Character.from_public_keys({SigningPower: alice_pubkey_bytes})

    somebody.verify_from(hearsay_alice, message, signature)

    hearsay_alice = Character.from_public_keys(verifying_key=alice_pubkey_bytes)

    somebody.verify_from(hearsay_alice, message, signature)
    alice.disenchant()
