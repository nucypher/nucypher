import pytest

from nkms.characters import Alice, Ursula, Character
from nkms.crypto import api
from nkms.crypto.constants import NOT_SIGNED

"""
SIGNING
"""

from nkms.crypto.constants import NO_DECRYPTION_PERFORMED
from nkms.crypto.powers import CryptoPower, SigningKeypair, NoSigningPower, NoEncryptingPower, \
    EncryptingPower


def test_actor_without_signing_power_cannot_sign():
    """
    We can create a Character with no real CryptoPower to speak of.
    This Character can't even sign a message.
    """
    cannot_sign = CryptoPower(power_ups=[])
    non_signer = Character(crypto_power=cannot_sign)

    # The non-signer's seal doesn't work for signing...
    with pytest.raises(NoSigningPower) as e_info:
        non_signer.seal("something")

    # ...or as a way to show the public key.
    with pytest.raises(NoSigningPower) as e_info:
        non_signer.seal.as_bytes()
    with pytest.raises(NoSigningPower) as e_info:
        non_signer.seal.as_tuple()


def test_actor_with_signing_power_can_sign():
    """
    However, simply giving that character a PowerUp bestows the power to sign.

    Instead of having a Character verify the signature, we'll use the lower level API.
    """
    message = b"Llamas."

    signer = Character(crypto_power_ups=[SigningKeypair])
    seal_of_the_signer = signer.seal

    # We can use the signer's seal to sign a message...
    signature = seal_of_the_signer(message)

    # ...or to get the signer's public key for verification purposes.
    sig = api.ecdsa_load_sig(signature)
    verification = api.ecdsa_verify(*sig, api.keccak_digest(message), seal_of_the_signer.as_tuple())

    assert verification is True


def test_anybody_can_verify():
    """
    In the last example, we used the lower-level Crypto API to verify the signature.

    Here, we show that anybody can do it without needing to directly access Crypto.
    """

    # Alice can sign by default, by dint of her _default_crypto_powerups.
    alice = Alice()

    # So, our story is fairly simple: an everyman meets Alice.
    somebody = Character()
    somebody.learn_about_actor(alice)

    # Alice signs a message.
    message = b"A message for all my friends who can only verify and not sign."
    signature = alice.seal(message)

    # Our everyman can verify it.
    verification, cleartext = somebody.verify_from(alice, signature, message, decrypt=False)
    assert verification is True
    assert cleartext is NO_DECRYPTION_PERFORMED

    # If we pass the signature and message backwards, we get TypeError.
    # with pytest.raises(TypeError):
    #    verification = somebody.verify_from(alice, message, signature)


"""
ENCRYPTION
"""


def test_signing_only_power_cannot_encrypt():
    """
    Similar to the above with signing, here we show that a Character without the EncryptingKeypair
    PowerUp can't encrypt.
    """

    # Here's somebody who can sign but not encrypt.
    can_sign_but_not_encrypt = Character(crypto_power_ups=[SigningKeypair])

    # ..and here's Ursula, for whom our Character above wants to encrypt.
    ursula = Ursula()

    # They meet.
    can_sign_but_not_encrypt.learn_about_actor(ursula)

    # The Character has the message ready...
    cleartext = "This is Officer Rod Farva. Come in, Ursula!  Come in Ursula!"

    # But without the proper PowerUp, no encryption happens.
    with pytest.raises(NoEncryptingPower) as e_info:
        can_sign_but_not_encrypt.encrypt_for(ursula, cleartext)


def test_character_with_encrypting_power_can_encrypt():
    """
    Now, a Character *with* EncryptingKeyPair can encrypt.
    """
    can_sign_and_encrypt = Character(crypto_power_ups=[SigningKeypair, EncryptingPower])
    ursula = Ursula()
    can_sign_and_encrypt.learn_about_actor(ursula)

    cleartext = b"This is Officer Rod Farva. Come in, Ursula!  Come in Ursula!"

    # TODO: Make encrypt_for actually encrypt.
    ciphertext, signature = can_sign_and_encrypt.encrypt_for(ursula, cleartext, sign=False)
    assert signature == NOT_SIGNED

    assert ciphertext is not None  # annnd fail.
