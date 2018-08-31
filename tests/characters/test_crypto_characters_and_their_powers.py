import eth_utils
import pytest
from constant_sorrow import constants

from nucypher.characters import Alice, Character, Bob
from nucypher.crypto import api
from nucypher.crypto.powers import CryptoPower, SigningPower, NoSigningPower, \
    BlockchainPower, PowerUpError

"""
Chapter 1: SIGNING
"""


def test_actor_without_signing_power_cannot_sign():
    """
    We can create a Character with no real CryptoPower to speak of.
    This Character can't even sign a message.
    """
    cannot_sign = CryptoPower(power_ups=[])
    non_signer = Character(crypto_power=cannot_sign,
                           always_be_learning=False,
                           federated_only=True)

    # The non-signer's stamp doesn't work for signing...
    with pytest.raises(NoSigningPower) as e_info:
        non_signer.stamp("something")

    # ...or as a way to cast the (non-existent) public key to bytes.
    with pytest.raises(NoSigningPower) as e_info:
        bytes(non_signer.stamp)


def test_actor_with_signing_power_can_sign():
    """
    However, simply giving that character a PowerUp bestows the power to sign.

    Instead of having a Character verify the signature, we'll use the lower level API.
    """
    message = b"Llamas."

    signer = Character(crypto_power_ups=[SigningPower], is_me=True,
                       always_be_learning=False, federated_only=True)
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
    alice = Alice(federated_only=True, always_be_learning=False)

    # So, our story is fairly simple: an everyman meets Alice.
    somebody = Character(always_be_learning=False, federated_only=True)

    # Alice signs a message.
    message = b"A message for all my friends who can only verify and not sign."
    signature = alice.stamp(message)

    # Our everyman can verify it.
    cleartext = somebody.verify_from(alice, message, signature, decrypt=False)
    assert cleartext is constants.NO_DECRYPTION_PERFORMED


def test_character_blockchain_power(testerchain):
    eth_address = testerchain.interface.w3.eth.accounts[0]
    sig_privkey = testerchain.interface._providers[0].ethereum_tester.backend. \
        _key_lookup[eth_utils.to_canonical_address(eth_address)]
    sig_pubkey = sig_privkey.public_key

    signer = Character(is_me=True, checksum_address=eth_address)
    signer._crypto_power.consume_power_up(BlockchainPower(testerchain, eth_address))

    # Due to testing backend, the account is already unlocked.
    power = signer._crypto_power.power_ups(BlockchainPower)
    power.is_unlocked = True
    # power.unlock_account('this-is-not-a-secure-password')

    data_to_sign = b'What does Ursula look like?!?'
    sig = power.sign_message(data_to_sign)

    is_verified = power.verify_message(eth_address, sig_pubkey.to_bytes(), data_to_sign, sig)
    assert is_verified == True

    # Test a bad message:
    with pytest.raises(PowerUpError):
        power.verify_message(eth_address, sig_pubkey.to_bytes(), data_to_sign + b'bad', sig)

    # Test a bad address/pubkey pair
    with pytest.raises(ValueError):
        power.verify_message(
            testerchain.interface.w3.eth.accounts[1],
            sig_pubkey.to_bytes(),
            data_to_sign,
            sig)

    # Test a signature without unlocking the account
    power.is_unlocked = False
    with pytest.raises(PowerUpError):
        power.sign_message(b'test')

    # Test lockAccount call
    del (power)


"""
Chapter 2: ENCRYPTION
"""


def test_anybody_can_encrypt():
    """
    Similar to anybody_can_verify() above; we show that anybody can encrypt.
    """
    someone = Character(always_be_learning=False, federated_only=True)
    bob = Bob(is_me=False, federated_only=True)

    cleartext = b"This is Officer Rod Farva. Come in, Ursula!  Come in Ursula!"

    ciphertext, signature = someone.encrypt_for(bob, cleartext, sign=False)

    assert signature == constants.NOT_SIGNED
    assert ciphertext is not None


def test_node_deployer(ursulas):
    for ursula in ursulas:
        deployer = ursula.get_deployer()
        assert deployer.options['https_port'] == ursula.rest_interface.port
        assert deployer.application == ursula.rest_app


"""
What follows are various combinations of signing and encrypting, to match
real-world scenarios.
"""


def test_sign_cleartext_and_encrypt(alice, bob):
    """
    Exhibit One: Alice signs the cleartext and encrypts her signature inside
    the ciphertext.
    """
    message = b"Have you accepted my answer on StackOverflow yet?"

    message_kit, _signature = alice.encrypt_for(bob, message,
                                                sign_plaintext=True)

    # Notice that our function still returns the signature here, in case Alice
    # wants to do something else with it, such as post it publicly for later
    # public verifiability.

    # However, we can expressly refrain from passing the Signature, and the
    # verification still works:
    cleartext = bob.verify_from(alice, message_kit, signature=None,
                                decrypt=True)
    assert cleartext == message


def test_encrypt_and_sign_the_ciphertext(alice, bob):
    """
    Now, Alice encrypts first and then signs the ciphertext, providing a
    Signature that is completely separate from the message.
    This is useful in a scenario in which Bob needs to prove authenticity
    publicly without disclosing contents.
    """
    message = b"We have a reaaall problem."
    message_kit, signature = alice.encrypt_for(bob, message,
                                               sign_plaintext=False)
    cleartext = bob.verify_from(alice, message_kit, signature, decrypt=True)
    assert cleartext == message


def test_encrypt_and_sign_including_signature_in_both_places(alice, bob):
    """
    Same as above, but showing that we can include the signature in both
    the plaintext (to be found upon decryption) and also passed into
    verify_from() (eg, gleaned over a side-channel).
    """
    message = b"We have a reaaall problem."
    message_kit, signature = alice.encrypt_for(bob, message,
                                               sign_plaintext=True)
    cleartext = bob.verify_from(alice, message_kit, signature,
                                decrypt=True)
    assert cleartext == message


def test_encrypt_but_do_not_sign(alice, bob):
    """
    Finally, Alice encrypts but declines to sign.
    This is useful in a scenario in which Alice wishes to plausibly disavow
    having created this content.
    """
    # TODO: How do we accurately demonstrate this test safely, if at all?
    message = b"If Bonnie comes home and finds an unencrypted private key in her keystore, I'm gonna get divorced."

    # Alice might also want to encrypt a message but *not* sign it, in order
    # to refrain from creating evidence that can prove she was the
    # original sender.
    message_kit, not_signature = alice.encrypt_for(bob, message, sign=False)

    # The message is not signed...
    assert not_signature == constants.NOT_SIGNED

    # ...and thus, the message is not verified.
    with pytest.raises(Character.InvalidSignature):
        bob.verify_from(alice, message_kit, decrypt=True)
