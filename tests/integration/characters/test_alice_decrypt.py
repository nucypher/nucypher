from nucypher.characters.lawful import Enrico


def test_alice_can_decrypt(alice):
    label = b"boring test label"

    policy_pubkey = alice.get_policy_encrypting_key_from_label(label)

    enrico = Enrico(encrypting_key=policy_pubkey)

    message = b"boring test message"
    message_kit = enrico.encrypt_for_pre(plaintext=message)

    # Interesting thing: if Alice wants to decrypt, she needs to provide the label directly.
    cleartexts = alice.decrypt_message_kit(label=label, message_kit=message_kit)
    assert cleartexts == [message]
