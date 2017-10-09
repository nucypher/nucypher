import random
import unittest

import msgpack
import npre.elliptic_curve as ec

from nkms.crypto.crypto import Crypto
from nkms.crypto.keystore import KeyStore
# from nacl.secret import SecretBox
from nkms.crypto.powers import CryptoPower, SigningKeypair


class TestKeyRing(unittest.TestCase):
    def setUp(self):
        self.power_of_signing = CryptoPower(power_ups=[SigningKeypair])
        self.keyring_a = KeyStore()
        self.keyring_b = KeyStore()

        self.msg = b'this is a test'

    def test_signing(self):
        signature = self.power_of_signing.sign(self.msg)

        sig = msgpack.loads(signature)
        self.assertTrue(1, len(sig[0]))  # Check v
        self.assertTrue(32, len(sig[1]))  # Check r
        self.assertTrue(32, len(sig[2]))  # Check s

    def test_verification(self):
        signature = self.power_of_signing.sign(self.msg)

        sig = msgpack.loads(signature)
        self.assertTrue(1, len(sig[0]))  # Check v
        self.assertTrue(32, len(sig[1]))  # Check r
        self.assertTrue(32, len(sig[2]))  # Check s

        msghash = Crypto.digest(self.msg)
        is_valid = Crypto.verify(signature, msghash,
                                 pubkey=self.power_of_signing.pubkey_sig_tuple())
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
        key = Crypto.secure_random(32)
        self.assertEqual(32, len(key))

        ciphertext = self.keyring_a.symm_encrypt(key, self.msg)
        self.assertTrue(self.msg not in ciphertext)

    def test_symm_decryption(self):
        key = Crypto.secure_random(32)
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

    def test_derive_path_key(self):
        return
        path = b'/foo/bar'

        path_priv_key = self.keyring_a._derive_path_key(path, is_pub=False)
        self.assertEqual(32, len(path_priv_key))

        path_pub_key = self.keyring_a._derive_path_key(path)
        self.assertEqual(32, len(path_pub_key))

        path_priv_key_int = int.from_bytes(path_priv_key, byteorder='big')
        verify_path_key = self.keyring_a.pre.priv2pub(path_priv_key_int)
        # TODO: Figure out why this returns 34 chars
        verify_path_key = ec.serialize(verify_path_key)[2:]
        self.assertEqual(32, len(verify_path_key))
        self.assertEqual(path_priv_key, path_priv_key)

    def test_encrypt_decrypt_reencrypt(self):
        plaintext = b'test'
        path = b'/'

        enc_keys = self.keyring_a.encrypt(plaintext, path=path)
        self.assertEqual(1, len(enc_keys))
        self.assertEqual(2, len(enc_keys[0]))

        path_priv_a = self.keyring_a._derive_path_key(b'', is_pub=False)
        path_priv_a = int.from_bytes(path_priv_a, byteorder='big')

        rk_ab, enc_symm_key_bob, enc_priv_e = self.keyring_a.rekey(
            path_priv_a, self.keyring_b.enc_pubkey)

        enc_path_key, enc_path_symm_key = enc_keys[0]
        reenc_path_symm_key = self.keyring_a.reencrypt(rk_ab, enc_path_symm_key)

        priv_e = self.keyring_b.decrypt(enc_priv_e, enc_symm_key_bob)
        priv_e = int.from_bytes(priv_e, byteorder='big')
        keyring_e = KeyStore(enc_privkey=priv_e)

        dec_key = keyring_e.decrypt(enc_path_key, reenc_path_symm_key)
        self.assertEqual(plaintext, dec_key)

    def test_encrypt_decrypt(self):
        plaintext = b'test'
        path = b'/'

        enc_keys = self.keyring_a.encrypt(plaintext, path=path)
        self.assertEqual(1, len(enc_keys))
        self.assertEqual(2, len(enc_keys[0]))

        path_priv_a = self.keyring_a._derive_path_key(b'', is_pub=False)
        path_priv_a = int.from_bytes(path_priv_a, byteorder='big')
        keyring_a_path = KeyStore(enc_privkey=path_priv_a)

        dec_key = keyring_a_path.decrypt(*enc_keys[0])
        self.assertEqual(plaintext, dec_key)

    def test_secure_random(self):
        length = random.randrange(1, 100)
        rand_bytes = Crypto.secure_random(length)
        self.assertEqual(length, len(rand_bytes))
