

from nucypher_core import MessageKit

from nucypher.characters.lawful import Enrico


def test_message_kit_serialization_via_enrico(alice):

    mock_label = b'this is a label'

    # Enrico
    enrico = Enrico.from_alice(alice, label=mock_label)

    # Plaintext
    message = 'this is a message'
    plaintext_bytes = bytes(message, encoding='utf-8')

    # Create
    message_kit = enrico.encrypt_message(plaintext=plaintext_bytes)

    # Serialize
    message_kit_bytes = bytes(message_kit)

    # Deserialize
    the_same_message_kit = MessageKit.from_bytes(message_kit_bytes)

    # Confirm
    assert message_kit_bytes == bytes(the_same_message_kit)
