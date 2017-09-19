import unittest
import msgpack
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
                                    pubkey=self.keyring_a.sig_keypair.pub_key)
        self.assertTrue(is_valid)

    def test_encryption(self):
        ciphertext = self.keyring_a.encrypt(self.msg,
                                    pubkey=self.keyring_b.enc_keypair.pub_key)
        self.assertNotEqual(self.msg, ciphertext)

    def test_decryption(self):
        ciphertext = self.keyring_a.encrypt(self.msg,
                                    pubkey=self.keyring_b.enc_keypair.pub_key)
        self.assertNotEqual(self.msg, ciphertext)

        plaintext = self.keyring_b.decrypt(ciphertext)
        self.assertEqual(self.msg, plaintext)
