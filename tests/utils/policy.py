

import os
import random

from nucypher.characters.lawful import Enrico


def generate_random_label() -> bytes:
    """
    Generates a random bytestring for use as a test label.
    :return: bytes
    """
    adjs = ('my', 'sesame-street', 'black', 'cute')
    nouns = ('lizard', 'super-secret', 'data', 'coffee')
    combinations = list('-'.join((a, n)) for a in adjs for n in nouns)
    selection = random.choice(combinations)
    random_label = f'label://{selection}-{os.urandom(4).hex()}'
    return bytes(random_label, encoding='utf-8')


def make_message_kits(policy_pubkey, conditions=None):
    messages = [b"plaintext1", b"plaintext2", b"plaintext3"]

    message_kits = []
    for message in messages:
        # Using different Enricos, because why not.
        enrico = Enrico(encrypting_key=policy_pubkey)
        message_kit = enrico.encrypt_for_pre(message, conditions=conditions)
        message_kits.append(message_kit)

    return messages, message_kits
