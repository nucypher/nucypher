import unittest
from nkms.keystore import keystore, keypairs


class TestKeyStore(unittest.TestCase):
    def setUp(self):
        self.ks = keystore.KeyStore()

    def test_ecies_keypair_generation(self):
        keypair = self.ks.gen_ecies_keypair()
        self.assertEqual(keypairs.EncryptingKeypair, type(keypair))
        self.assertEqual(bytes, type(keypair.privkey))
        self.assertEqual(bytes, type(keypair.pubkey))

    def test_ecdsa_keypair_generation(self):
        keypair = self.ks.gen_ecdsa_keypair()
        self.assertEqual(keypairs.SigningKeypair, type(keypair))
        self.assertEqual(bytes, type(keypair.privkey))
        self.assertEqual(bytes, type(keypair.pubkey))

    def test_get_key(self):
        # TODO: Implement this.
        pass

    def test_add_key(self):
        # TODO: Implement this.
        pass

    def test_del_key(self):
        # TODO: Implement this.
        pass
