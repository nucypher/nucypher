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

import os
import random
import string

from nucypher.characters.lawful import Enrico
from nucypher.crypto.powers import DecryptingPower


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


def retrieval_request_setup(enacted_policy, bob, alice, encode_for_rest=False):

    treasure_map = bob._decrypt_treasure_map(enacted_policy.treasure_map,
                                             enacted_policy.publisher_verifying_key)

    # We pick up our story with Bob already having followed the treasure map above, ie:
    bob.start_learning_loop()

    bob.follow_treasure_map(treasure_map=treasure_map, block=True, timeout=1)

    # We'll test against just a single Ursula - here, we make a WorkOrder for just one.
    # We can pass any number of capsules as args; here we pass just one.
    enrico = Enrico(policy_encrypting_key=enacted_policy.public_key)
    original_message = ''.join(random.choice(string.ascii_lowercase) for i in range(20))  # random message
    message_kit = enrico.encrypt_message(original_message.encode())

    # Shouldn't the controller be able to do it?
    encode_bytes = (lambda x: bytes(x)) if encode_for_rest else (lambda x: x)

    return dict(treasure_map=encode_bytes(treasure_map),
                retrieval_kits=[encode_bytes(message_kit.as_retrieval_kit())],
                alice_verifying_key=encode_bytes(alice.stamp.as_umbral_pubkey()),
                bob_encrypting_key=encode_bytes(bob.public_keys(DecryptingPower)),
                bob_verifying_key=encode_bytes(bob.stamp.as_umbral_pubkey()),
                policy_encrypting_key=encode_bytes(enacted_policy.public_key),
                )
