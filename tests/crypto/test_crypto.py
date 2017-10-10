import unittest
import random
from nacl.utils import EncryptedMessage
from npre import umbral
from npre import elliptic_curve as ec
from nkms.crypto import crypto as Crypto


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

    def test_secure_random(self):
        rand1 = Crypto.secure_random(10)
        rand2 = Crypto.secure_random(10)

        self.assertNotEqual(rand1, rand2)
        self.assertEqual(bytes, type(rand1))
        self.assertEqual(bytes, type(rand2))
        self.assertEqual(10, len(rand1))
        self.assertEqual(10, len(rand2))

    def test_secure_random_range(self):
        output = [Crypto.secure_random_range(1, 3) for _ in range(20)]

        # Test that highest output can be max-1
        self.assertNotIn(3, output)

        # Test that min is present
        output = [Crypto.secure_random_range(1, 2) for _ in range(20)]
        self.assertNotIn(2, output)
        self.assertIn(1, output)

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
        self.assertEqual(bytes, type(key))
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
        self.assertEqual(bytes, type(key))
        self.assertEqual(32, len(key))

        dec_key = Crypto.ecies_decapsulate(self.privkey_a, enc_key)
        self.assertEqual(bytes, type(dec_key))
        self.assertEqual(32, len(dec_key))
        self.assertEqual(key, dec_key)

        # Check from bytes
        key, enc_key = Crypto.ecies_encapsulate(self.pubkey_a_bytes)
        self.assertNotEqual(key, enc_key)
        self.assertEqual(umbral.EncryptedKey, type(enc_key))
        self.assertEqual(bytes, type(key))
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

    def test_ecies_split_rekey(self):
        # Check w/o conversion
        frags = Crypto.ecies_split_rekey(self.privkey_a, self.privkey_b, 3, 4)
        self.assertEqual(list, type(frags))
        self.assertEqual(4, len(frags))

        # Check with conversion
        frags = Crypto.ecies_split_rekey(self.privkey_a_bytes,
                                         self.privkey_b_bytes, 3, 4)
        self.assertEqual(list, type(frags))
        self.assertEqual(4, len(frags))

    def test_ecies_combine(self):
        eph_priv = self.pre.gen_priv()
        eph_pub = self.pre.priv2pub(eph_priv)

        plain_key, enc_key = Crypto.ecies_encapsulate(eph_pub)
        self.assertNotEqual(plain_key, enc_key)
        self.assertEqual(umbral.EncryptedKey, type(enc_key))
        self.assertEqual(bytes, type(plain_key))
        self.assertEqual(32, len(plain_key))

        rk_frags = Crypto.ecies_split_rekey(eph_priv, self.privkey_b, 6, 10)
        self.assertEqual(list, type(rk_frags))
        self.assertEqual(10, len(rk_frags))

        rk_selected = random.sample(rk_frags, 6)
        shares = [Crypto.ecies_reencrypt(rk_frag, enc_key) for rk_frag in rk_selected]
        self.assertEqual(list, type(shares))
        self.assertEqual(6, len(shares))
        [self.assertEqual(umbral.EncryptedKey, type(share)) for share in shares]

        e_b = Crypto.ecies_combine(shares)
        self.assertEqual(umbral.EncryptedKey, type(e_b))

        dec_key = Crypto.ecies_decapsulate(self.privkey_b, e_b)
        self.assertEqual(bytes, type(dec_key))
        self.assertEqual(32, len(dec_key))
        self.assertEqual(plain_key, dec_key)

    def test_ecies_reencrypt(self):
        eph_priv = self.pre.gen_priv()
        eph_pub = self.pre.priv2pub(eph_priv)

        plain_key, enc_key = Crypto.ecies_encapsulate(eph_pub)
        self.assertNotEqual(plain_key, enc_key)
        self.assertEqual(umbral.EncryptedKey, type(enc_key))
        self.assertEqual(bytes, type(plain_key))
        self.assertEqual(32, len(plain_key))

        rk_eb = Crypto.ecies_rekey(eph_priv, self.privkey_b,
                                   to_bytes=False)
        self.assertEqual(umbral.RekeyFrag, type(rk_eb))
        self.assertEqual(ec.ec_element, type(rk_eb.key))

        reenc_key = Crypto.ecies_reencrypt(rk_eb, enc_key)
        dec_key = Crypto.ecies_decapsulate(self.privkey_b, reenc_key)
        self.assertEqual(plain_key, dec_key)
