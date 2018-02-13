import random
import unittest

import sha3
from nacl.utils import EncryptedMessage

from nkms.crypto import api


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
        rand1 = api.secure_random(10)
        rand2 = api.secure_random(10)

        self.assertNotEqual(rand1, rand2)
        self.assertEqual(bytes, type(rand1))
        self.assertEqual(bytes, type(rand2))
        self.assertEqual(10, len(rand1))
        self.assertEqual(10, len(rand2))

    def test_secure_random_range(self):
        output = [api.secure_random_range(1, 3) for _ in range(20)]

        # Test that highest output can be max-1
        self.assertNotIn(3, output)

        # Test that min is present
        output = [api.secure_random_range(1, 2) for _ in range(20)]
        self.assertNotIn(2, output)
        self.assertIn(1, output)

    def test_keccak_digest(self):
        data = b'this is a test'

        digest1 = sha3.keccak_256(data).digest()
        digest2 = api.keccak_digest(data)

        self.assertEqual(digest1, digest2)

        # Test iterables
        data = data.split()

        digest1 = sha3.keccak_256(b''.join(data)).digest()
        digest2 = api.keccak_digest(*data)

        self.assertEqual(digest1, digest2)

    def test_ecdsa_pub2bytes(self):
        privkey = api.ecdsa_gen_priv()
        self.assertEqual(32, len(privkey))

        pubkey = api.ecdsa_priv2pub(privkey, to_bytes=False)
        self.assertEqual(tuple, type(pubkey))
        self.assertEqual(2, len(pubkey))
        self.assertEqual(int, type(pubkey[0]))
        self.assertEqual(int, type(pubkey[1]))

        pubkey = api.ecdsa_pub2bytes(pubkey)
        self.assertEqual(bytes, type(pubkey))

    def test_ecdsa_bytes2pub(self):
        privkey = api.ecdsa_gen_priv()
        self.assertEqual(32, len(privkey))

        pubkey_tuple = api.ecdsa_priv2pub(privkey, to_bytes=False)
        self.assertEqual(tuple, type(pubkey_tuple))
        self.assertEqual(2, len(pubkey_tuple))
        self.assertEqual(int, type(pubkey_tuple[0]))
        self.assertEqual(int, type(pubkey_tuple[1]))

        pubkey_bytes = api.ecdsa_priv2pub(privkey)
        self.assertEqual(bytes, type(pubkey_bytes))

        pubkey = api.ecdsa_bytes2pub(pubkey_bytes[PublicKey._METABYTES_LENGTH::])
        self.assertEqual(tuple, type(pubkey))
        self.assertEqual(2, len(pubkey))
        self.assertEqual(int, type(pubkey[0]))
        self.assertEqual(int, type(pubkey[1]))

        self.assertEqual(pubkey_tuple, pubkey)

    def test_ecdsa_gen_priv(self):
        privkey = api.ecdsa_gen_priv()
        self.assertEqual(bytes, type(privkey))
        self.assertEqual(32, len(privkey))

    def test_ecdsa_priv2pub(self):
        privkey = api.ecdsa_gen_priv()
        self.assertEqual(bytes, type(privkey))
        self.assertEqual(32, len(privkey))

        # Test Serialization
        pubkey = api.ecdsa_priv2pub(privkey)
        self.assertEqual(bytes, type(pubkey))
        self.assertEqual(PublicKey._EXPECTED_LENGTH, len(pubkey))

        # Test no serialization
        pubkey = api.ecdsa_priv2pub(privkey, to_bytes=False)
        self.assertEqual(tuple, type(pubkey))
        self.assertEqual(2, len(pubkey))
        self.assertEqual(int, type(pubkey[0]))
        self.assertEqual(int, type(pubkey[1]))

    def test_ecdsa_gen_sig(self):
        v, r, s = 1, 2, 3

        sig = api.ecdsa_gen_sig(v, r, s)
        self.assertEqual(bytes, type(sig))

    def test_ecdsa_load_sig(self):
        v = 1
        r = int.from_bytes(api.secure_random(32), byteorder='big')
        s = int.from_bytes(api.secure_random(32), byteorder='big')

        sig = api.ecdsa_gen_sig(v, r, s)
        self.assertEqual(bytes, type(sig))
        self.assertEqual(65, len(sig))

        loaded_sig = api.ecdsa_load_sig(sig)
        self.assertEqual(tuple, type(loaded_sig))
        self.assertEqual(3, len(loaded_sig))
        self.assertEqual((v, r, s), loaded_sig)

    def test_ecdsa_sign(self):
        msghash = api.secure_random(32)
        privkey = api.ecdsa_gen_priv()

        vrs = api.ecdsa_sign(msghash, privkey)
        self.assertEqual(tuple, type(vrs))
        self.assertEqual(3, len(vrs))

    def test_ecdsa_verify(self):
        msghash = api.secure_random(32)
        privkey = api.ecdsa_gen_priv()
        pubkey = api.ecdsa_priv2pub(privkey, to_bytes=False)

        vrs = api.ecdsa_sign(msghash, privkey)
        self.assertEqual(tuple, type(vrs))
        self.assertEqual(3, len(vrs))

        is_verified = api.ecdsa_verify(*vrs, msghash, pubkey)
        self.assertEqual(bool, type(is_verified))
        self.assertTrue(is_verified)

    def test_symm_encrypt(self):
        key = api.secure_random(32)
        plaintext = b'this is a test'

        ciphertext = api.symm_encrypt(key, plaintext)
        self.assertEqual(EncryptedMessage, type(ciphertext))
        self.assertNotEqual(plaintext, ciphertext)

    def test_symm_decrypt(self):
        key = api.secure_random(32)
        plaintext = b'this is a test'

        ciphertext = api.symm_encrypt(key, plaintext)
        self.assertEqual(EncryptedMessage, type(ciphertext))
        self.assertNotEqual(plaintext, ciphertext)

        dec_text = api.symm_decrypt(key, ciphertext)
        self.assertEqual(bytes, type(dec_text))
        self.assertNotEqual(ciphertext, dec_text)
        self.assertEqual(plaintext, dec_text)

    def test_priv_bytes2ec(self):
        full_privkey_bytes = ec.serialize(self.privkey_a)
        privkey_bytes = full_privkey_bytes[1:]

        if len(privkey_bytes) is not 32:
            # Debug information here.
            print("Hey everybody!  Here's the weird len31 bug.  The bytes were {}.".format(full_privkey_bytes))

        self.assertEqual(bytes, type(privkey_bytes))
        self.assertEqual(32, len(privkey_bytes))

        privkey = api.priv_bytes2ec(privkey_bytes)
        self.assertEqual(ec.ec_element, type(privkey))
        self.assertEqual(self.privkey_a, privkey)

    def test_pub_bytes2ec(self):
        pubkey = self.pre.priv2pub(self.privkey_a)
        self.assertEqual(ec.ec_element, type(pubkey))

        pubkey_bytes = ec.serialize(pubkey)[1:]
        self.assertEqual(bytes, type(pubkey_bytes))
        self.assertEqual(33, len(pubkey_bytes))

        pubkey_ec = api.pub_bytes2ec(pubkey_bytes)
        self.assertEqual(ec.ec_element, type(pubkey_ec))
        self.assertEqual(pubkey_ec, pubkey)

    def test_ecies_gen_priv(self):
        # Check serialiation first
        privkey = api.ecies_gen_priv()
        self.assertEqual(bytes, type(privkey))
        self.assertEqual(32, len(privkey))

        # Check no serialization
        privkey = api.ecies_gen_priv(to_bytes=False)
        self.assertEqual(ec.ec_element, type(privkey))

    def test_ecies_priv2pub(self):
        # Check serialization first
        pubkey = api.ecies_priv2pub(self.privkey_a)
        self.assertEqual(bytes, type(pubkey))
        self.assertEqual(33, len(pubkey))

        # Check no serialization
        pubkey = api.ecies_priv2pub(self.privkey_a_bytes, to_bytes=False)
        self.assertEqual(ec.ec_element, type(pubkey))

    def test_ecies_encapsulate(self):
        # Check from ec.element
        key, enc_key = api.ecies_encapsulate(self.pubkey_a)
        self.assertNotEqual(key, enc_key)
        self.assertEqual(umbral.EncryptedKey, type(enc_key))
        self.assertEqual(bytes, type(key))
        self.assertEqual(32, len(key))

        # Check from bytes
        key, enc_key = api.ecies_encapsulate(self.pubkey_a_bytes)
        self.assertNotEqual(key, enc_key)
        self.assertEqual(umbral.EncryptedKey, type(enc_key))
        self.assertEqual(32, len(key))

    def test_ecies_decapsulate(self):
        # Check from ec.element
        key, enc_key = api.ecies_encapsulate(self.pubkey_a)
        self.assertNotEqual(key, enc_key)
        self.assertEqual(umbral.EncryptedKey, type(enc_key))
        self.assertEqual(bytes, type(key))
        self.assertEqual(32, len(key))

        dec_key = api.ecies_decapsulate(self.privkey_a, enc_key)
        self.assertEqual(bytes, type(dec_key))
        self.assertEqual(32, len(dec_key))
        self.assertEqual(key, dec_key)

        # Check from bytes
        key, enc_key = api.ecies_encapsulate(self.pubkey_a_bytes)
        self.assertNotEqual(key, enc_key)
        self.assertEqual(umbral.EncryptedKey, type(enc_key))
        self.assertEqual(bytes, type(key))
        self.assertEqual(32, len(key))

        dec_key = api.ecies_decapsulate(self.privkey_a, enc_key)
        self.assertEqual(bytes, type(dec_key))
        self.assertEqual(32, len(dec_key))
        self.assertEqual(key, dec_key)

    def test_ecies_rekey(self):
        # Check serialization first
        rekey = api.ecies_rekey(self.privkey_a, self.privkey_b)
        self.assertEqual(bytes, type(rekey))
        self.assertEqual(32, len(rekey))

        # Check no serialization
        rekey = api.ecies_rekey(self.privkey_a_bytes, self.privkey_b_bytes,
                                to_bytes=False)
        self.assertEqual(umbral.RekeyFrag, type(rekey))
        self.assertEqual(ec.ec_element, type(rekey.key))

    def test_ecies_split_rekey(self):
        # Check w/o conversion
        frags = api.ecies_split_rekey(self.privkey_a, self.privkey_b, 3, 4)
        self.assertEqual(list, type(frags))
        self.assertEqual(4, len(frags))

        # Check with conversion
        frags = api.ecies_split_rekey(self.privkey_a_bytes,
                                      self.privkey_b_bytes, 3, 4)
        self.assertEqual(list, type(frags))
        self.assertEqual(4, len(frags))

    def test_ecies_ephemeral_split_rekey(self):
        frags, enc_eph_data = api.ecies_ephemeral_split_rekey(self.privkey_a,
                                                              self.pubkey_b,
                                                              3, 4)
        self.assertEqual(list, type(frags))
        self.assertEqual(4, len(frags))

        self.assertEqual(PFrag._EXPECTED_LENGTH, len(enc_eph_data))
        self.assertEqual(umbral.EncryptedKey, type(enc_eph_data.deserialized()[0]))
        self.assertEqual(EncryptedMessage, type(enc_eph_data.deserialized()[1]))

    def test_ecies_combine(self):
        eph_priv = self.pre.gen_priv()
        eph_pub = self.pre.priv2pub(eph_priv)

        plain_key, enc_key = api.ecies_encapsulate(eph_pub)
        self.assertNotEqual(plain_key, enc_key)
        self.assertEqual(umbral.EncryptedKey, type(enc_key))
        self.assertEqual(bytes, type(plain_key))
        self.assertEqual(32, len(plain_key))

        rk_frags = api.ecies_split_rekey(eph_priv, self.privkey_b, 6, 10)
        self.assertEqual(list, type(rk_frags))
        self.assertEqual(10, len(rk_frags))

        rk_selected = random.sample(rk_frags, 6)
        shares = [api.ecies_reencrypt(rk_frag, enc_key) for rk_frag in rk_selected]
        self.assertEqual(list, type(shares))
        self.assertEqual(6, len(shares))

        e_b = api.ecies_combine(shares)
        self.assertEqual(umbral.EncryptedKey, type(e_b))

        dec_key = api.ecies_decapsulate(self.privkey_b, e_b)
        self.assertEqual(bytes, type(dec_key))
        self.assertEqual(32, len(dec_key))
        self.assertEqual(plain_key, dec_key)

    def test_ecies_reencrypt(self):
        eph_priv = self.pre.gen_priv()
        eph_pub = self.pre.priv2pub(eph_priv)

        plain_key, enc_key = api.ecies_encapsulate(eph_pub)
        self.assertNotEqual(plain_key, enc_key)
        self.assertEqual(umbral.EncryptedKey, type(enc_key))
        self.assertEqual(bytes, type(plain_key))
        self.assertEqual(32, len(plain_key))

        rk_eb = api.ecies_rekey(eph_priv, self.privkey_b,
                                to_bytes=False)
        self.assertEqual(umbral.RekeyFrag, type(rk_eb))
        self.assertEqual(ec.ec_element, type(rk_eb.key))

        cfrag = api.ecies_reencrypt(rk_eb, enc_key)
        dec_key = api.ecies_decapsulate(self.privkey_b, cfrag.encrypted_key)
        self.assertEqual(plain_key, dec_key)
