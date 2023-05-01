

import unittest

from eth_utils import keccak

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

        digest1 = keccak(data)
        digest2 = keccak_digest(data)

        self.assertEqual(digest1, digest2)

        # Test iterables
        data = data.split()

        digest1 = keccak(b''.join(data))
        digest2 = keccak_digest(*data)

        self.assertEqual(digest1, digest2)
