import unittest
from nkms.keystore import keypairs


class TestKeypairs(unittest.TestCase):
    def setUp(self):
        self.ecies_keypair = keypairs.EncryptingKeypair()
        self.ecdsa_keypair = keypairs.SigningKeypair()

    def test_ecies_keypair_generation(self):
        self.ecies_keypair.gen_privkey()

        self.assertTrue(self.ecies_keypair.privkey is not None)
        self.assertEqual(bytes, type(self.ecies_keypair.privkey))
        self.assertEqual(32, len(self.ecies_keypair.privkey))

        self.assertTrue(self.ecies_keypair.pubkey is not None)
        self.assertEqual(bytes, type(self.ecies_keypair.pubkey))
        self.assertEqual(33, len(self.ecies_keypair.pubkey))

    def test_ecdsa_keypair_generation(self):
        self.ecdsa_keypair.gen_privkey()

        self.assertTrue(self.ecdsa_keypair.privkey is not None)
        self.assertEqual(bytes, type(self.ecdsa_keypair.privkey))
        self.assertEqual(32, len(self.ecdsa_keypair.privkey))

        self.assertTrue(self.ecdsa_keypair.pubkey is not None)
        self.assertEqual(bytes, type(self.ecdsa_keypair.pubkey))
        self.assertEqual(64, len(self.ecdsa_keypair.pubkey))
