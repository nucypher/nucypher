"""
This file is part of nucypher.

nucypher is free software: you can redistribute it and/or modify
it under the terms of the GNU Affero General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

nucypher is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU Affero General Public License for more details.

You should have received a copy of the GNU Affero General Public License
along with nucypher.  If not, see <https://www.gnu.org/licenses/>.
"""


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
    message_kit = federated_alice.encrypt_for(federated_alice, message, sign_plaintext=True)
    cleartext = federated_alice.decrypt_message_kit(federated_alice, message_kit)
    assert cleartext == message


def test_encrypt_and_sign_the_ciphertext(federated_alice, federated_bob):
    """
    Now, federated_alice encrypts first and then signs the ciphertext, providing a
    Signature that is completely separate from the message.
    This is useful in a scenario in which federated_bob needs to prove authenticity
    publicly without disclosing contents.
    """
    message = b"We have a reaaall problem."
    message_kit = federated_alice.encrypt_for(federated_alice, message, sign_plaintext=False)
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
