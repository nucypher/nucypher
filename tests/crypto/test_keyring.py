import unittest
import msgpack
import random
from nkms.crypto.keyring import KeyRing


class TestKeyRing(unittest.TestCase):
    def setUp(self):
        self.keyring_a = KeyRing()
        self.keyring_b = KeyRing()

        self.msg = b'this is a test'

    def test_signing(self):
        signature = self.keyring_a.sign(self.msg)

        sig = msgpack.loads(signature)
        self.assertTrue(1, len(sig[0]))     # Check v
        self.assertTrue(32, len(sig[1]))    # Check r
        self.assertTrue(32, len(sig[2]))    # Check s

    def test_verification(self):
        signature = self.keyring_a.sign(self.msg)

        sig = msgpack.loads(signature)
        self.assertTrue(1, len(sig[0]))     # Check v
        self.assertTrue(32, len(sig[1]))    # Check r
        self.assertTrue(32, len(sig[2]))    # Check s

        is_valid = self.keyring_b.verify(self.msg, signature,
                                         pubkey=self.keyring_a.sig_pubkey)
        self.assertTrue(is_valid)

    def test_key_generation(self):
        raw_key, enc_key = self.keyring_a.generate_key()
        self.assertEqual(32, len(raw_key))
        self.assertTrue(raw_key != enc_key)

    def test_key_decryption(self):
        raw_key, enc_key = self.keyring_a.generate_key()
        self.assertEqual(32, len(raw_key))
        self.assertTrue(raw_key != enc_key)

        dec_key = self.keyring_a.decrypt_key(enc_key)
        self.assertTrue(32, len(dec_key))
        self.assertTrue(raw_key == dec_key)

    def test_secure_random(self):
        length = random.randrange(1, 100)
        rand_bytes = self.keyring_a.secure_random(length)
        self.assertEqual(length, len(rand_bytes))
