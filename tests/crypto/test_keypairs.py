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

    def test_key_gen(self):
        raw_symm, enc_symm = self.send_keypair.generate_key()
        self.assertEqual(32, len(raw_symm))
        self.assertTrue(raw_symm != enc_symm)

    def test_key_decryption(self):
        raw_symm, enc_symm = self.send_keypair.generate_key()
        self.assertEqual(32, len(raw_symm))
        self.assertTrue(raw_symm != enc_symm)

        dec_symm_key = self.send_keypair.decrypt_key(enc_symm)
        self.assertEqual(32, len(dec_symm_key))
        self.assertTrue(raw_symm == dec_symm_key)

    def test_reencryption(self):
        raw_symm, enc_symm = self.send_keypair.generate_key()
        self.assertEqual(32, len(raw_symm))
        self.assertTrue(raw_symm != enc_symm)

        rekey_ab = self.send_keypair.rekey(self.send_keypair.priv_key,
                                           self.recv_keypair.priv_key)
        reenc_key = self.send_keypair.reencrypt(rekey_ab, enc_symm)
        self.assertTrue(reenc_key != enc_symm)

        dec_key = self.recv_keypair.decrypt_key(reenc_key)
        self.assertEqual(32, len(dec_key))
        self.assertTrue(dec_key == raw_symm)
