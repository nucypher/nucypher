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
