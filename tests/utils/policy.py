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
from nucypher.policy.orders import WorkOrder


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


def work_order_setup(enacted_policy,
                     ursulas,
                     bob,
                     alice):

    # We pick up our story with Bob already having followed the treasure map above, ie:
    treasure_map = enacted_policy.treasure_map
    bob.start_learning_loop()

    bob.follow_treasure_map(treasure_map=treasure_map, block=True, timeout=1)

    assert len(bob.known_nodes) == len(ursulas)

    # Bob has no saved work orders yet, ever.
    assert len(bob._completed_work_orders) == 0

    # We'll test against just a single Ursula - here, we make a WorkOrder for just one.
    # We can pass any number of capsules as args; here we pass just one.
    enrico = Enrico(policy_encrypting_key=enacted_policy.public_key)
    original_message = ''.join(random.choice(string.ascii_lowercase) for i in range(20))  # random message
    message_kit, _ = enrico.encrypt_message(original_message.encode())
    message_kit.set_correctness_keys(delegating=enacted_policy.public_key,
                                     receiving=bob.public_keys(DecryptingPower),
                                     verifying=alice.stamp.as_umbral_pubkey())
    work_orders, _ = bob.work_orders_for_capsules(
        message_kit.capsule,
        label=enacted_policy.label,
        treasure_map=treasure_map,
        alice_verifying_key=alice.stamp.as_umbral_pubkey(),
        num_ursulas=1)

    # Again: one Ursula, one work_order.
    assert len(work_orders) == 1
    ursula_address, work_order = list(work_orders.items())[0]
    return ursula_address, work_order
