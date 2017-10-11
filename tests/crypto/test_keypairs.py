import unittest
import sha3
import msgpack
import random

from nkms.crypto import api
from nkms.crypto.keypairs import EncryptingKeypair
from nkms.crypto.powers import SigningKeypair


class TestSigningKeypair(unittest.TestCase):
    def setUp(self):
        self.keypair_a = SigningKeypair()
        self.keypair_b = SigningKeypair()
        self.msg = b'this is a test'

    def test_signing(self):
        msg_digest = sha3.keccak_256(self.msg).digest()
        signature = self.keypair_a.sign(msg_digest)

        sig = api.ecdsa_load_sig(signature)
        self.assertEqual(tuple, type(sig))
        self.assertEqual(int, type(sig[0]))     # Check v
        self.assertEqual(int, type(sig[1]))    # Check r
        self.assertEqual(int, type(sig[2]))    # Check s

    def test_verification(self):
        msg_digest = sha3.keccak_256(self.msg).digest()
        signature = self.keypair_a.sign(msg_digest)

        sig = api.ecdsa_load_sig(signature)
        self.assertEqual(int, type(sig[0]))     # Check v
        self.assertEqual(int, type(sig[1]))    # Check r
        self.assertEqual(int, type(sig[2]))    # Check s

        verify_sig = api.ecdsa_verify(*sig, msg_digest,
                                           self.keypair_a.pub_key)
        self.assertTrue(verify_sig)

    def test_digest(self):
        digest_a = api.keccak_digest(b'foo', b'bar')
        digest_b = api.keccak_digest(b'foobar')

        self.assertEqual(digest_a, digest_b)


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

    def test_split_rekey(self):
        raw_symm, enc_symm = self.send_keypair.generate_key()
        self.assertEqual(32, len(raw_symm))
        self.assertTrue(raw_symm != enc_symm)

        enc_shares = self.send_keypair.split_rekey(self.send_keypair.priv_key,
                                                   self.recv_keypair.priv_key,
                                                   4, 10)
        self.assertEqual(10, len(enc_shares))

        rand_shares = random.sample(enc_shares, 4)
        self.assertEqual(4, len(rand_shares))

        frags = [self.send_keypair.reencrypt(rk, enc_symm) for rk in rand_shares]
        self.assertEqual(4, len(frags))

        enc_key = self.recv_keypair.combine(frags)
        self.assertTrue(raw_symm != enc_key)
        self.assertTrue(enc_symm != enc_key)

        dec_key = self.recv_keypair.decrypt_key(enc_key)
        self.assertTrue(dec_key == raw_symm)
