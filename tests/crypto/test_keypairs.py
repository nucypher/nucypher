import unittest
import sha3
import msgpack
from nkms.crypto.keypairs import SigningKeypair, EncryptingKeypair


class TestSigningKeypair(unittest.TestCase):
    def setUp(self):
        self.keypair_a = SigningKeypair()
        self.keypair_b = SigningKeypair()
        self.msg = b'this is a test'

    def test_signing(self):
        msg_digest = sha3.keccak_256(self.msg).digest()
        signature = self.keypair_a.sign(msg_digest)

        sig = msgpack.loads(signature)
        self.assertTrue(1, len(sig[0]))     # Check v
        self.assertTrue(32, len(sig[1]))    # Check r
        self.assertTrue(32, len(sig[2]))    # Check s

    def test_verification(self):
        msg_digest = sha3.keccak_256(self.msg).digest()
        signature = self.keypair_a.sign(msg_digest)

        sig = msgpack.loads(signature)
        self.assertTrue(1, len(sig[0]))     # Check v
        self.assertTrue(32, len(sig[1]))    # Check r
        self.assertTrue(32, len(sig[2]))    # Check s

        verify_sig = self.keypair_b.verify(msg_digest, signature,
                                           pubkey=self.keypair_a.pub_key)
        self.assertTrue(verify_sig)


class TestEncryptingKeypair(unittest.TestCase):
    def setUp(self):
        self.send_keypair = EncryptingKeypair()
        self.recv_keypair = EncryptingKeypair()
        self.msg = b'this is a test'

    def test_encryption(self):
        ciphertext = self.send_keypair.encrypt(self.msg,
                pubkey=self.recv_keypair.pub_key)
        self.assertNotEqual(self.msg, ciphertext)

    def test_decryption(self):
        ciphertext = self.send_keypair.encrypt(self.msg,
                pubkey=self.recv_keypair.pub_key)
        self.assertNotEqual(self.msg, ciphertext)

        plaintext = self.recv_keypair.decrypt(ciphertext)
        self.assertEqual(self.msg, plaintext)
