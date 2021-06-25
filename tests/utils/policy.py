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

import random
import os

from bytestring_splitter import VariableLengthBytestring

from nucypher.policy.collections import WorkOrder
from nucypher.policy.policies import Arrangement


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


def work_order_setup(mock_ursula_reencrypts,
                     ursulas,
                     bob,
                     alice):
    ursula = list(ursulas)[0]
    tasks = [mock_ursula_reencrypts(ursula) for _ in range(3)]
    material = [(task.capsule, task.signature, task.cfrag, task.cfrag_signature) for task in tasks]
    capsules, signatures, cfrags, cfrag_signatures = zip(*material)

    arrangement_id = os.urandom(Arrangement.ID_LENGTH)
    work_order = WorkOrder.construct_by_bob(arrangement_id=arrangement_id,
                                            bob=bob,
                                            alice_verifying=alice.stamp.as_umbral_pubkey(),
                                            ursula=ursula,
                                            capsules=capsules)
    # mimic actual reencrypt call (for now)
    expected_response_bytes = bytes()
    cfrags_and_signatures = list(zip(cfrags, cfrag_signatures))
    for cfrag, signature in cfrags_and_signatures:
        expected_response_bytes += VariableLengthBytestring(cfrag) + signature
    return ursula, work_order, expected_response_bytes
