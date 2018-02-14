import pytest

from nkms.characters import Alice, Ursula, Character
from nkms.crypto import api
from nkms.crypto.constants import NOT_SIGNED
from nkms.crypto.constants import NO_DECRYPTION_PERFORMED
from nkms.crypto.powers import CryptoPower, SigningPower, NoSigningPower, \
    NoEncryptingPower, \
    EncryptingPower

"""
Chapter 1: SIGNING
"""


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

    # ...or as a way to cast the public key to bytes or tuple.
    with pytest.raises(NoSigningPower) as e_info:
        bytes(non_signer.seal)
    with pytest.raises(NoSigningPower) as e_info:
        tuple(non_signer.seal)


def test_actor_with_signing_power_can_sign():
    """
    However, simply giving that character a PowerUp bestows the power to sign.

    Instead of having a Character verify the signature, we'll use the lower level API.
    """
    message = b"Llamas."

    signer = Character(crypto_power_ups=[SigningPower], is_me=True)
    seal_of_the_signer = signer.seal

    # We can use the signer's seal to sign a message (since the signer is_me)...
    signature = seal_of_the_signer(message)

    # ...or to get the signer's public key for verification purposes.
    # (note: we use the private _der_encoded_bytes here to test directly against the API, instead of Character)
    verification = api.ecdsa_verify(message, signature._der_encoded_bytes(),
                                    seal_of_the_signer.as_umbral_pubkey())

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
    verification, cleartext = somebody.verify_from(alice, message, signature, decrypt=False)
    assert verification is True
    assert cleartext is NO_DECRYPTION_PERFORMED

    # If we pass the signature and message backwards, we get TypeError.
    # with pytest.raises(TypeError):
    #    verification = somebody.verify_from(alice, message, signature)


"""
Chapter 2: ENCRYPTION
"""

def test_anybody_can_encrypt():
    """
    Similar to anybody_can_verify() above; we show that anybody can encrypt.
    """
    can_sign_and_encrypt = Character(crypto_power_ups=[SigningPower, EncryptingPower])
    ursula = Ursula()
    can_sign_and_encrypt.learn_about_actor(ursula)

    cleartext = b"This is Officer Rod Farva. Come in, Ursula!  Come in Ursula!"

    ciphertext, signature = can_sign_and_encrypt.encrypt_for(ursula, cleartext, sign=False)
    assert signature == NOT_SIGNED

    assert ciphertext is not None
