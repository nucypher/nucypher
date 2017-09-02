import unittest
from nkms.crypto import kmac
from nacl.utils import random


class TestKMAC256(unittest.TestCase):
    def setUp(self):
        self.KMAC = kmac.KMAC_256()

    def test_256_bit_constants(self):
        self.assertEqual(32, self.KMAC.LENGTH_BYTES)
        self.assertEqual(136, self.KMAC.BLOCK_SIZE_BYTES)

    def test_bytepad(self):
        rand_bytes = random(32)
        # Padding to 64 bytes, its an arbitrary number I picked for testing.
        padded_rand_bytes = self.KMAC._bytepad(rand_bytes, 64)
        self.assertTrue(64, len(padded_rand_bytes))
        
        # Check the formatting
        w = int.from_bytes(padded_rand_bytes[:2], byteorder='big')
        self.assertEqual(64, w)
        pad = padded_rand_bytes[34:]
        self.assertEqual(bytes(len(pad)), pad)
