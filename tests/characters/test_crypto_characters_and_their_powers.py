import pytest

from nkms.characters import Alice, Ursula, Character
from nkms.crypto import api
from nkms.crypto.constants import NOT_SIGNED
from nkms.crypto.constants import NO_DECRYPTION_PERFORMED
from nkms.crypto.powers import CryptoPower, SigningPower, NoSigningPower, \
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

    # The non-signer's stamp doesn't work for signing...
    with pytest.raises(NoSigningPower) as e_info:
        non_signer.stamp("something")

    # ...or as a way to cast the public key to bytes or tuple.
    with pytest.raises(NoSigningPower) as e_info:
        bytes(non_signer.stamp)
    with pytest.raises(NoSigningPower) as e_info:
        tuple(non_signer.stamp)


def test_actor_with_signing_power_can_sign():
    """
    However, simply giving that character a PowerUp bestows the power to sign.

    Instead of having a Character verify the signature, we'll use the lower level API.
    """
    message = b"Llamas."

    signer = Character(crypto_power_ups=[SigningPower], is_me=True)
    stamp_of_the_signer = signer.stamp

    # We can use the signer's stamp to sign a message (since the signer is_me)...
    signature = stamp_of_the_signer(message)

    # ...or to get the signer's public key for verification purposes.
    # (note: we use the private _der_encoded_bytes here to test directly against the API, instead of Character)
    verification = api.ecdsa_verify(message, signature._der_encoded_bytes(),
                                    stamp_of_the_signer.as_umbral_pubkey())

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
    signature = alice.stamp(message)

    # Our everyman can verify it.
    verification, cleartext = somebody.verify_from(alice, message, signature, decrypt=False)
    assert verification is True
    assert cleartext is NO_DECRYPTION_PERFORMED

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

"""
What follows are various combinations of signing and encrypting, to match real-world scenarios.
"""

def test_sign_cleartext_and_encrypt(alice, bob):
    """
    Exhibit One: Alice signs the cleartext and encrypts her signature inside the ciphertext.
    """
    message = b"Have you accepted my answer on StackOverflow yet?"

    message_kit, _signature = alice.encrypt_for(bob, message, sign_plaintext=True)

    # Notice that our function still returns the signature here, in case Alice wants to do something
    # else with it, such as post it publicly for later public verifiability.

    # However, we can expressly refrain from passing the Signature, and the verification still works:
    verified, cleartext = bob.verify_from(alice, message_kit, signature=None, decrypt=True,
                                          signature_is_on_cleartext=True)
    assert verified
    assert cleartext == message


def test_encrypt_and_sign_the_ciphertext(alice, bob):
    """
    Now, Alice encrypts first and then signs the ciphertext, providing a Signature that is
    completely separate from the message.
    This is useful in a scenario in which Bob needs to prove authenticity publicly
    without disclosing contents.
    """
    message = b"We have a reaaall problem."
    message_kit, signature = alice.encrypt_for(bob, message, sign_plaintext=False)
    verified, cleartext = bob.verify_from(alice, message_kit, signature,
                                          signature_is_on_cleartext=False, decrypt=True)
    assert verified
    assert cleartext == message


def test_encrypt_but_do_not_sign(alice, bob):
    message = b"If Bonnie comes home and finds an unencrypted private key in her keystore, I'm gonna get divorced."

    # Alice might also want to encrypt a message but *not* sign it, in order to refrain
    # from creating evidence that can prove she was the original sender.
    message_kit, not_signature = alice.encrypt_for(bob, message, sign=False)

    # The message is not signed...
    assert not_signature == NOT_SIGNED

    verified, cleartext = bob.verify_from(alice, message_kit, decrypt=True)

    # ...and thus, the message is not verified.
    assert cleartext == message

    # However, the message was properly decrypted.
    assert message == cleartext


