import unittest
import msgpack
import random
import npre.elliptic_curve as ec
from nkms.crypto.keyring import KeyRing
from nacl.secret import SecretBox


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

    def test_rekey_and_reencryption(self):
        # Generate random key for Alice's data
        symm_key_alice, enc_symm_key_alice = self.keyring_a.generate_key()

        # Generate the re-encryption key and the ephemeral key data
        reenc_key, enc_symm_key_bob, enc_priv_e = self.keyring_a.rekey(
                                                    self.keyring_a.enc_privkey,
                                                    self.keyring_b.enc_pubkey)

        # Re-encrypt Alice's symm key
        enc_symm_key_ab = self.keyring_a.reencrypt(reenc_key,
                                                   enc_symm_key_alice)

        # Decapsulate the ECIES encrypted key
        dec_symm_key_bob = self.keyring_b.decrypt_key(enc_symm_key_bob)
        self.assertEqual(32, len(dec_symm_key_bob))

        # Decrypt the ephemeral private key
        dec_priv_e = self.keyring_b.symm_decrypt(dec_symm_key_bob, enc_priv_e)
        self.assertEqual(32, len(dec_priv_e))
        dec_priv_e = int.from_bytes(dec_priv_e, byteorder='big')

        dec_key = self.keyring_b.decrypt_key(enc_symm_key_ab,
                                             privkey=dec_priv_e)

        self.assertEqual(dec_key, symm_key_alice)

    def test_split_key_sharing(self):
        raw_key, enc_key = self.keyring_a.generate_key()
        self.assertTrue(32, len(raw_key))

        shares = self.keyring_a.gen_split_rekey(self.keyring_a.enc_privkey,
                                                self.keyring_b.enc_privkey,
                                                4, 10)
        self.assertEqual(10, len(shares))

        rand_shares = random.sample(shares, 4)
        self.assertEqual(4, len(rand_shares))

        frags = [self.keyring_a.reencrypt(rk, enc_key) for rk in rand_shares]
        self.assertEqual(4, len(frags))

        split_enc_key = self.keyring_b.build_secret(frags)
        self.assertTrue(raw_key != split_enc_key)
        self.assertTrue(enc_key != split_enc_key)

        dec_key = self.keyring_b.decrypt_key(split_enc_key)
        self.assertEqual(32, len(dec_key))
        self.assertTrue(dec_key == raw_key)

    def test_symm_encryption(self):
        key = self.keyring_a.secure_random(32)
        self.assertEqual(32, len(key))

        ciphertext = self.keyring_a.symm_encrypt(key, self.msg)
        self.assertTrue(self.msg not in ciphertext)

    def test_symm_decryption(self):
        key = self.keyring_a.secure_random(32)
        self.assertEqual(32, len(key))

        ciphertext = self.keyring_a.symm_encrypt(key, self.msg)
        self.assertTrue(self.msg not in ciphertext)

        plaintext = self.keyring_a.symm_decrypt(key, ciphertext)
        self.assertTrue(self.msg == plaintext)

    def test_split_path(self):
        subpaths = self.keyring_a._split_path(b'/foo/bar')
        self.assertEqual(3, len(subpaths))
        self.assertTrue(b'' in subpaths)
        self.assertTrue(b'/foo' in subpaths)
        self.assertTrue(b'/foo/bar' in subpaths)

        subpaths = self.keyring_a._split_path(b'foobar')
        self.assertEqual(1, len(subpaths))
        self.assertTrue(b'foobar' in subpaths)

        subpaths = self.keyring_a._split_path(b'')
        self.assertEqual(1, len(subpaths))
        self.assertTrue(b'' in subpaths)

    def test_secure_random(self):
        length = random.randrange(1, 100)
        rand_bytes = self.keyring_a.secure_random(length)
        self.assertEqual(length, len(rand_bytes))
