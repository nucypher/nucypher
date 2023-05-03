


import pytest
from constant_sorrow import constants

from nucypher.characters.lawful import Enrico

"""
What follows are various combinations of signing and encrypting, to match
real-world scenarios.
"""


def test_sign_cleartext_and_encrypt(alice, bob):
    """
    Exhibit One: alice signs the cleartext and encrypts her signature inside
    the ciphertext.
    """
    message = b"Have you accepted my answer on StackOverflow yet?"
    message_kit = alice.encrypt_for(alice, message)
    cleartext = alice.decrypt_message_kit(alice, message_kit)
    assert cleartext == message


def test_alice_can_decrypt(alice):
    label = b"boring test label"

    policy_pubkey = alice.get_policy_encrypting_key_from_label(label)

    enrico = Enrico(encrypting_key=policy_pubkey)

    message = b"boring test message"
    message_kit = enrico.encrypt_for_pre(plaintext=message)

    # Interesting thing: if Alice wants to decrypt, she needs to provide the label directly.
    cleartexts = alice.decrypt_message_kit(label=label, message_kit=message_kit)
    assert cleartexts == [message]
