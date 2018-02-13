import unittest
from nacl.utils import EncryptedMessage
from nkms.crypto import api


class TestInternal(unittest.TestCase):
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

    def test_ecies_gen_ephemeral_key(self):
        result_data = _internal._ecies_gen_ephemeral_key(
                                            self.pubkey_a)
        self.assertEqual(tuple, type(result_data))
        self.assertEqual(2, len(result_data))

        eph_privkey, enc_data = result_data

        self.assertEqual(bytes, type(eph_privkey))
        self.assertEqual(32, len(eph_privkey))

        self.assertEqual(tuple, type(enc_data))
        self.assertEqual(2, len(enc_data))

        enc_symm_key, enc_eph_key = enc_data

        self.assertEqual(umbral.EncryptedKey, type(enc_symm_key))
        self.assertEqual(EncryptedMessage, type(enc_eph_key))
        self.assertNotEqual(eph_privkey, enc_eph_key)

        dec_symm_key = api.ecies_decapsulate(self.privkey_a, enc_symm_key)

        self.assertEqual(bytes, type(dec_symm_key))
        self.assertEqual(32, len(dec_symm_key))

        dec_eph_key = api.symm_decrypt(dec_symm_key, enc_eph_key)

        self.assertEqual(bytes, type(dec_eph_key))
        self.assertEqual(32, len(dec_eph_key))
        self.assertEqual(eph_privkey, dec_eph_key)
