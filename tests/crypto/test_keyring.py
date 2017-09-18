import unittest
import msgpack
from nkms.crypto.keyring import KeyRing


class TestKeyRing(unittest.TestCase):
    def setUp(self):
        self.keyring = KeyRing()
        self.msg = b'this is a test'

    def test_signing(self):
        signature = self.keyring.sign(self.msg)

        try:
            sig = msgpack.loads(signature)
            self.assertTrue(1, len(sig[0]))     # Check v
            self.assertTrue(32, len(sig[1]))    # Check r
            self.assertTrue(32, len(sig[2]))    # Check s
        except Exception as e:
            self.fail("Signature failed to msgpack.loads: {}".format(e))

    def test_verification(self):
        signature = self.keyring.sign(self.msg)

        try:
            sig = msgpack.loads(signature)
            self.assertTrue(1, len(sig[0]))     # Check v
            self.assertTrue(32, len(sig[1]))    # Check r
            self.assertTrue(32, len(sig[2]))    # Check s
        except Exception as e:
            self.fail("Signature failed to msgpack.loads: {}".format(e))

        is_valid = self.keyring.verify(self.msg, signature)
        self.assertTrue(is_valid)
