import pytest

from nkms.characters import Alice, Ursula, Character
from nkms.crypto import crypto as Crypto
from nkms.crypto.powers import CryptoPower, SigningKeypair, NoSigningPower, NoEncryptingPower


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
    verification = Crypto.verify(signature, Crypto.digest(message), seal_of_the_signer.as_tuple())

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
    verification = somebody.verify_from(alice, signature, message)
    assert verification is True


def test_signing_only_power_cannot_encrypt():
    """
    Similar to the above with signing, here we show that a Character without the EncryptingKeypair
    PowerUp can't encrypt.
    """

    # Here's somebody who can sign but not encrypt.
    can_sign_but_not_encrypt = Character(crypto_power_ups=[SigningKeypair])

    # ..and here's Ursula, for whom our Character above wants to encrypt.
    ursula = Ursula()
    ursula.pubkey_collection = {'signing': "some_privkey_sig"}

    # They meet.
    can_sign_but_not_encrypt.learn_about_actor(ursula)


    # The Character has the message ready...
    cleartext = "This is Officer Rod Farva. Come in, Ursula!  Come in Ursula!"

    # But without the proper PowerUp, no encryption happens.
    with pytest.raises(NoEncryptingPower) as e_info:
        can_sign_but_not_encrypt.encrypt_for(ursula, cleartext)
