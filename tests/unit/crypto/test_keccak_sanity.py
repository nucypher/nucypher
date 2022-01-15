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

import unittest

import sha3

from nucypher.crypto.utils import (
    secure_random_range,
    secure_random,
    keccak_digest
)


class TestCrypto(unittest.TestCase):

    def test_secure_random(self):
        rand1 = secure_random(10)
        rand2 = secure_random(10)

        self.assertNotEqual(rand1, rand2)
        self.assertEqual(bytes, type(rand1))
        self.assertEqual(bytes, type(rand2))
        self.assertEqual(10, len(rand1))
        self.assertEqual(10, len(rand2))

    def test_secure_random_range(self):
        output = [secure_random_range(1, 3) for _ in range(20)]

        # Test that highest output can be max-1
        self.assertNotIn(3, output)

        # Test that min is present
        output = [secure_random_range(1, 2) for _ in range(20)]
        self.assertNotIn(2, output)
        self.assertIn(1, output)

    def test_keccak_digest(self):
        data = b'this is a test'

        digest1 = sha3.keccak_256(data).digest()
        digest2 = keccak_digest(data)

        self.assertEqual(digest1, digest2)

        # Test iterables
        data = data.split()

        digest1 = sha3.keccak_256(b''.join(data)).digest()
        digest2 = keccak_digest(*data)

        self.assertEqual(digest1, digest2)
