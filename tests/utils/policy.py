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
from typing import Dict, List, Optional, Tuple

from nucypher_core import MessageKit, RetrievalKit

from nucypher.characters.lawful import Enrico
from nucypher.control.specifications.fields import JSON
from nucypher.crypto.powers import DecryptingPower
from nucypher.utilities.porter.control.specifications.fields import (
    RetrievalKit as RetrievalKitField, Key,
)
from nucypher.utilities.porter.control.specifications.fields.treasuremap import TreasureMap


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


def retrieval_request_setup(enacted_policy,
                            bob,
                            alice,
                            specific_messages: Optional[List[bytes]] = None,
                            context: Optional[Dict] = None,
                            encode_for_rest: bool = False,
                            num_random_messages: int = None) -> Tuple[Dict, List[MessageKit]]:
    """
    Creates dict of values for a retrieval request. If no specific messages or number
    of random messages are provided, a single random message is encrypted.
    """
    if specific_messages and num_random_messages is not None:
        raise ValueError(
            "Provide either original_message or num_random_messages parameter, not both."
        )
    if not specific_messages and num_random_messages is None:
        # default to one random message
        num_random_messages = 1

    treasure_map = bob._decrypt_treasure_map(
        enacted_policy.treasure_map, enacted_policy.publisher_verifying_key
    )

    # We pick up our story with Bob already having followed the treasure map above, ie:
    bob.start_learning_loop()

    # We can pass any number of capsules as args; here we pass just one.
    enrico = Enrico(policy_encrypting_key=enacted_policy.public_key)
    message_kits = []
    if specific_messages:
        for message in specific_messages:
            message_kits.append(enrico.encrypt_message(message))
    else:
        for i in range(num_random_messages):
            random_message = "".join(
                random.choice(string.ascii_lowercase) for j in range(20)
            ).encode()  # random message
            message_kits.append(enrico.encrypt_message(random_message))

    encode_bytes = (lambda field, obj: field()._serialize(value=obj, attr=None, obj=None)) if encode_for_rest else (lambda field, obj: obj)

    retrieval_params = dict(
        treasure_map=encode_bytes(TreasureMap, treasure_map),
        retrieval_kits=[
            encode_bytes(RetrievalKitField, RetrievalKit.from_message_kit(message_kit))
            for message_kit in message_kits
        ],
        alice_verifying_key=encode_bytes(Key, alice.stamp.as_umbral_pubkey()),
        bob_encrypting_key=encode_bytes(Key, bob.public_keys(DecryptingPower)),
        bob_verifying_key=encode_bytes(Key, bob.stamp.as_umbral_pubkey()),
    )
    # context is optional
    if context:
        retrieval_params["context"] = encode_bytes(JSON, context)

    return retrieval_params, message_kits


def retrieval_params_decode_from_rest(retrieval_params: Dict) -> Dict:
    decode_bytes = lambda field, data: field()._deserialize(
        value=data, attr=None, data=None
    )
    decoded_params = dict(
        treasure_map=decode_bytes(TreasureMap, retrieval_params["treasure_map"]),
        retrieval_kits=[
            decode_bytes(RetrievalKitField, kit)
            for kit in retrieval_params["retrieval_kits"]
        ],
        alice_verifying_key=decode_bytes(Key, retrieval_params["alice_verifying_key"]),
        bob_encrypting_key=decode_bytes(Key, retrieval_params["bob_encrypting_key"]),
        bob_verifying_key=decode_bytes(Key, retrieval_params["bob_verifying_key"]),
    )
    # context is optional
    if "context" in retrieval_params:
        decoded_params["context"] = decode_bytes(
            JSON, retrieval_params["context"]
        )

    return decoded_params
