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
from typing import Dict

from nucypher.characters.control.specifications.fields import Key, DecryptedTreasureMap
from nucypher.characters.lawful import Enrico
from nucypher.crypto.powers import DecryptingPower
from nucypher.utilities.porter.control.specifications.fields import RetrievalKit


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


def retrieval_request_setup(enacted_policy, bob, alice, encode_for_rest=False) -> Dict:

    treasure_map = bob._decrypt_treasure_map(enacted_policy.treasure_map)

    # We pick up our story with Bob already having followed the treasure map above, ie:
    bob.start_learning_loop()

    bob.follow_treasure_map(treasure_map=treasure_map, block=True, timeout=1)
    decrypted_map = treasure_map.as_decrypted_map()

    # We'll test against just a single Ursula - here, we make a WorkOrder for just one.
    # We can pass any number of capsules as args; here we pass just one.
    enrico = Enrico(policy_encrypting_key=enacted_policy.public_key)
    original_message = ''.join(random.choice(string.ascii_lowercase) for i in range(20))  # random message
    message_kit = enrico.encrypt_message(original_message.encode())

    encode_bytes = (lambda field, obj: field()._serialize(value=obj, attr=None, obj=None)) if encode_for_rest else (lambda field, obj: obj)

    return dict(treasure_map=encode_bytes(DecryptedTreasureMap, decrypted_map),
                retrieval_kits=[encode_bytes(RetrievalKit, message_kit.as_retrieval_kit())],
                alice_verifying_key=encode_bytes(Key, alice.stamp.as_umbral_pubkey()),
                bob_encrypting_key=encode_bytes(Key, bob.public_keys(DecryptingPower)),
                bob_verifying_key=encode_bytes(Key, bob.stamp.as_umbral_pubkey()),
                policy_encrypting_key=encode_bytes(Key, enacted_policy.public_key))


def retrieval_params_decode_from_rest(retrieval_params: Dict) -> Dict:
    decode_bytes = (lambda field, data: field()._deserialize(value=data, attr=None, data=None))
    return dict(treasure_map=decode_bytes(DecryptedTreasureMap, retrieval_params['treasure_map']),
                retrieval_kits=[decode_bytes(RetrievalKit, kit) for kit in retrieval_params['retrieval_kits']],
                alice_verifying_key=decode_bytes(Key, retrieval_params['alice_verifying_key']),
                bob_encrypting_key=decode_bytes(Key, retrieval_params['bob_encrypting_key']),
                bob_verifying_key=decode_bytes(Key, retrieval_params['bob_verifying_key']),
                policy_encrypting_key=decode_bytes(Key, retrieval_params['policy_encrypting_key']))
