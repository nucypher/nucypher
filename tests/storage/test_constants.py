import unittest
from nkms.storage import constants


class TestConstants(unittest.TestCase):
    def test_constants(self):
        self.assertEqual(4, constants.NONCE_COUNTER_BYTE_SIZE)
        self.assertEqual(20, constants.NONCE_RANDOM_PREFIX_SIZE)
