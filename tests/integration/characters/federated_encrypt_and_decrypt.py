


import pytest
from constant_sorrow import constants

from nucypher.characters.lawful import Enrico

"""
What follows are various combinations of signing and encrypting, to match
real-world scenarios.
"""


def test_sign_cleartext_and_encrypt(federated_alice, federated_bob):
    """
    Exhibit One: federated_alice signs the cleartext and encrypts her signature inside
    the ciphertext.
    """
    message = b"Have you accepted my answer on StackOverflow yet?"
    message_kit = federated_alice.encrypt_for(federated_alice, message)
    cleartext = federated_alice.decrypt_message_kit(federated_alice, message_kit)
    assert cleartext == message


def test_alice_can_decrypt(federated_alice):
    label = b"boring test label"

    policy_pubkey = federated_alice.get_policy_encrypting_key_from_label(label)

    enrico = Enrico(policy_encrypting_key=policy_pubkey)

    message = b"boring test message"
    message_kit = enrico.encrypt_message(plaintext=message)

    # Interesting thing: if Alice wants to decrypt, she needs to provide the label directly.
    cleartexts = federated_alice.decrypt_message_kit(label=label,
                                                     message_kit=message_kit)
    assert cleartexts == [message]
