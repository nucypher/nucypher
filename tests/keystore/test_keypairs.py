import unittest
from nkms.keystore import keypairs


class TestKeypairs(unittest.TestCase):
    def setUp(self):
        self.ecies_keypair = keypairs.EncryptingKeypair()
        self.ecdsa_keypair = keypairs.SigningKeypair()

    def test_ecies_keypair_generation(self):
        self.ecies_keypair.gen_privkey()

        self.assertTrue(self.ecies_keypair.privkey != None)
        self.assertEqual(bytes, type(self.ecies_keypair.privkey))
        self.assertEqual(32, len(self.ecies_keypair.privkey))

        self.assertTrue(self.ecies_keypair.pubkey != None)
        self.assertEqual(bytes, type(self.ecies_keypair.pubkey))
        self.assertEqual(33, len(self.ecies_keypair.pubkey))
