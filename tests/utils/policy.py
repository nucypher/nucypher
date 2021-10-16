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
from typing import Dict, Tuple

from nucypher.core import MessageKit, RetrievalKit

from nucypher.characters.control.specifications.fields import Key, TreasureMap
from nucypher.characters.lawful import Enrico
from nucypher.crypto.powers import DecryptingPower
from nucypher.utilities.porter.control.specifications.fields import RetrievalKit as RetrievalKitField


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


def retrieval_request_setup(enacted_policy, bob, alice,  original_message: bytes = None, encode_for_rest: bool = False) -> Tuple[Dict, MessageKit]:
    treasure_map = bob._decrypt_treasure_map(enacted_policy.treasure_map,
                                             enacted_policy.publisher_verifying_key)

    # We pick up our story with Bob already having followed the treasure map above, ie:
    bob.start_learning_loop()

    # We can pass any number of capsules as args; here we pass just one.
    enrico = Enrico(policy_encrypting_key=enacted_policy.public_key)
    if not original_message:
        original_message = ''.join(random.choice(string.ascii_lowercase) for i in range(20)).encode()  # random message
    message_kit = enrico.encrypt_message(original_message)

    encode_bytes = (lambda field, obj: field()._serialize(value=obj, attr=None, obj=None)) if encode_for_rest else (lambda field, obj: obj)

    return (dict(treasure_map=encode_bytes(TreasureMap, treasure_map),
                 retrieval_kits=[encode_bytes(RetrievalKitField, RetrievalKit.from_message_kit(message_kit))],
                 alice_verifying_key=encode_bytes(Key, alice.stamp.as_umbral_pubkey()),
                 bob_encrypting_key=encode_bytes(Key, bob.public_keys(DecryptingPower)),
                 bob_verifying_key=encode_bytes(Key, bob.stamp.as_umbral_pubkey())),
            message_kit)


def retrieval_params_decode_from_rest(retrieval_params: Dict) -> Dict:
    decode_bytes = (lambda field, data: field()._deserialize(value=data, attr=None, data=None))
    return dict(treasure_map=decode_bytes(TreasureMap, retrieval_params['treasure_map']),
                retrieval_kits=[decode_bytes(RetrievalKitField, kit) for kit in retrieval_params['retrieval_kits']],
                alice_verifying_key=decode_bytes(Key, retrieval_params['alice_verifying_key']),
                bob_encrypting_key=decode_bytes(Key, retrieval_params['bob_encrypting_key']),
                bob_verifying_key=decode_bytes(Key, retrieval_params['bob_verifying_key']))
