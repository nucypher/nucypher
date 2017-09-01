import unittest
from nacl.utils import random
from nkms.client import Client
from nkms.crypto import (default_algorithm, pre_from_algorithm,
    symmetric_from_algorithm, kmac)


class TestClient(unittest.TestCase):
    def setUp(self):
        self.pre = pre_from_algorithm(default_algorithm)
        self.priv_key = self.pre.gen_priv(dtype='bytes')
        self.pub_key = self.pre.priv2pub(self._priv_key)

        self.client = Client()

    def test_derive_path_key(self):
        path = '/foo/bar'
        derived_path_key = self.client._derive_path_key(path)
        self.assertEqual(bytes, type(derived_path_key))

    def test_encrypt_key_with_path_tuple(self):
        key = random(32)
        path = ('/', '/foo', '/foo/bar')

        enc_keys = self.client.encrypt_key(key, path=path)
        self.assertEqual(3, len(enc_keys))
        self.assertTrue(key not in enc_keys)

    def test_encrypt_key_with_path_string(self):
        key = random(32)
        path = 'foobar'

        enc_key = self.client.encrypt_key(key, path)
        self.assertNotEqual(key, enc_key)

    def test_encrypt_key_no_path(self):
        key = random(32)

        # Use client's pubkey (implict)
        enc_key_1 = self.client.encrypt_key(key)
        self.assertNotEqual(key, enc_key)

        # Use provided pubkey (explicit)
        enc_ke_2 = self.client.encrypt_key(key, pubkey=pubkey)
        self.assertNotEqual(key, enc_key)
        self.assertNotEqual(enc_key_1, enc_key_2)
