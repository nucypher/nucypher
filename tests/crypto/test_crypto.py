import unittest
import random
from nacl.utils import EncryptedMessage
from npre import umbral
from npre import elliptic_curve as ec
from nkms.crypto.crypto import Crypto


class TestCrypto(unittest.TestCase):
    def setUp(self):
        self.pre = umbral.PRE()
        self.privkey_a = self.pre.gen_priv()
        self.privkey_a_bytes = ec.serialize(self.privkey_a)[1:]

        self.privkey_b = self.pre.gen_priv()
        self.privkey_b_bytes = ec.serialize(self.privkey_b)[1:]

        self.pubkey_a = self.pre.priv2pub(self.privkey_a)
        self.pubkey_b = self.pre.priv2pub(self.privkey_b)

        self.pubkey_a_bytes = ec.serialize(self.pubkey_a)[1:]
        self.pubkey_b_bytes = ec.serialize(self.pubkey_b)[1:]

    def test_priv_bytes2ec(self):
        privkey_bytes = ec.serialize(self.privkey_a)[1:]
        self.assertEqual(bytes, type(privkey_bytes))
        self.assertEqual(32, len(privkey_bytes))

        privkey = Crypto.priv_bytes2ec(privkey_bytes)
        self.assertEqual(ec.ec_element, type(privkey))
        self.assertEqual(self.privkey_a, privkey)

    def test_pub_bytes2ec(self):
        pubkey = self.pre.priv2pub(self.privkey_a)
        self.assertEqual(ec.ec_element, type(pubkey))

        pubkey_bytes = ec.serialize(pubkey)[1:]
        self.assertEqual(bytes, type(pubkey_bytes))
        self.assertEqual(33, len(pubkey_bytes))

        pubkey_ec = Crypto.pub_bytes2ec(pubkey_bytes)
        self.assertEqual(ec.ec_element, type(pubkey_ec))
        self.assertEqual(pubkey_ec, pubkey)

    def test_symm_encrypt(self):
        key = random._urandom(32)
        plaintext = b'this is a test'

        ciphertext = Crypto.symm_encrypt(key, plaintext)
        self.assertEqual(EncryptedMessage, type(ciphertext))
        self.assertNotEqual(plaintext, ciphertext)

    def test_symm_decrypt(self):
        key = random._urandom(32)
        plaintext = b'this is a test'

        ciphertext = Crypto.symm_encrypt(key, plaintext)
        self.assertEqual(EncryptedMessage, type(ciphertext))
        self.assertNotEqual(plaintext, ciphertext)

        dec_text = Crypto.symm_decrypt(key, ciphertext)
        self.assertEqual(bytes, type(dec_text))
        self.assertNotEqual(ciphertext, dec_text)
        self.assertEqual(plaintext, dec_text)

    def test_ecies_gen_priv(self):
        # Check serialiation first
        privkey = Crypto.ecies_gen_priv()
        self.assertEqual(bytes, type(privkey))
        self.assertEqual(32, len(privkey))

        # Check no serialization
        privkey = Crypto.ecies_gen_priv(to_bytes=False)
        self.assertEqual(ec.ec_element, type(privkey))

    def test_ecies_priv2pub(self):
        # Check serialization first
        pubkey = Crypto.ecies_priv2pub(self.privkey_a)
        self.assertEqual(bytes, type(pubkey))
        self.assertEqual(33, len(pubkey))

        # Check no serialization
        pubkey = Crypto.ecies_priv2pub(self.privkey_a_bytes, to_bytes=False)
        self.assertEqual(ec.ec_element, type(pubkey))

    def test_ecies_encapsulate(self):
        # Check from ec.element
        key, enc_key = Crypto.ecies_encapsulate(self.pubkey_a)
        self.assertNotEqual(key, enc_key)
        self.assertEqual(umbral.EncryptedKey, type(enc_key))
        self.assertEqual(32, len(key))

        # Check from bytes
        key, enc_key = Crypto.ecies_encapsulate(self.pubkey_a_bytes)
        self.assertNotEqual(key, enc_key)
        self.assertEqual(umbral.EncryptedKey, type(enc_key))
        self.assertEqual(32, len(key))

    def test_ecies_decapsulate(self):
        # Check from ec.element
        key, enc_key = Crypto.ecies_encapsulate(self.pubkey_a)
        self.assertNotEqual(key, enc_key)
        self.assertEqual(umbral.EncryptedKey, type(enc_key))
        self.assertEqual(32, len(key))

        dec_key = Crypto.ecies_decapsulate(self.privkey_a, enc_key)
        self.assertEqual(bytes, type(dec_key))
        self.assertEqual(32, len(dec_key))
        self.assertEqual(key, dec_key)

        # Check from bytes
        key, enc_key = Crypto.ecies_encapsulate(self.pubkey_a_bytes)
        self.assertNotEqual(key, enc_key)
        self.assertEqual(umbral.EncryptedKey, type(enc_key))
        self.assertEqual(32, len(key))

        dec_key = Crypto.ecies_decapsulate(self.privkey_a, enc_key)
        self.assertEqual(bytes, type(dec_key))
        self.assertEqual(32, len(dec_key))
        self.assertEqual(key, dec_key)

    def test_ecies_rekey(self):
        # Check serialization first
        rekey = Crypto.ecies_rekey(self.privkey_a, self.privkey_b)
        self.assertEqual(bytes, type(rekey))
        self.assertEqual(32, len(rekey))

        # Check no serialization
        rekey = Crypto.ecies_rekey(self.privkey_a_bytes, self.privkey_b_bytes,
                                   to_bytes=False)
        self.assertEqual(umbral.RekeyFrag, type(rekey))
        self.assertEqual(ec.ec_element, type(rekey.key))
