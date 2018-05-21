
import unittest

import sha3

from nucypher.crypto import api


class TestCrypto(unittest.TestCase):

    def test_secure_random(self):
        rand1 = api.secure_random(10)
        rand2 = api.secure_random(10)

        self.assertNotEqual(rand1, rand2)
        self.assertEqual(bytes, type(rand1))
        self.assertEqual(bytes, type(rand2))
        self.assertEqual(10, len(rand1))
        self.assertEqual(10, len(rand2))

    def test_secure_random_range(self):
        output = [api.secure_random_range(1, 3) for _ in range(20)]

        # Test that highest output can be max-1
        self.assertNotIn(3, output)

        # Test that min is present
        output = [api.secure_random_range(1, 2) for _ in range(20)]
        self.assertNotIn(2, output)
        self.assertIn(1, output)

    def test_keccak_digest(self):
        data = b'this is a test'

        digest1 = sha3.keccak_256(data).digest()
        digest2 = api.keccak_digest(data)

        self.assertEqual(digest1, digest2)

        # Test iterables
        data = data.split()

        digest1 = sha3.keccak_256(b''.join(data)).digest()
        digest2 = api.keccak_digest(*data)

        self.assertEqual(digest1, digest2)
