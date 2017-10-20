import unittest
import sha3
from nkms.keystore import keystore, keypairs


class TestKeyStore(unittest.TestCase):
    def setUp(self):
        self.ks = keystore.KeyStore('test')

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

    def test_lmdb_keystore(self):
        keypair = self.ks.gen_ecies_keypair()
        self.assertEqual(keypairs.EncryptingKeypair, type(keypair))
        self.assertEqual(bytes, type(keypair.privkey))
        self.assertEqual(bytes, type(keypair.pubkey))

        # Test add_key pubkey
        fingerprint_pub = self.ks.add_key(keypair, store_pub=True)
        self.assertEqual(bytes, type(fingerprint_pub))
        self.assertEqual(64, len(fingerprint_pub))

        key_hash = sha3.keccak_256(keypair.pubkey).hexdigest().encode()
        self.assertEqual(key_hash, fingerprint_pub)

        # Test add_key privkey
        fingerprint_priv = self.ks.add_key(keypair, store_pub=False)
        self.assertEqual(bytes, type(fingerprint_priv))
        self.assertEqual(64, len(fingerprint_priv))

        key_hash = sha3.keccak_256(keypair.privkey).hexdigest().encode()
        self.assertEqual(key_hash, fingerprint_priv)

        # Test get_key pubkey
        keypair_pub = self.ks.get_key(fingerprint_pub)
        self.assertEqual(keypairs.EncryptingKeypair, type(keypair_pub))
        self.assertTrue(keypair_pub.public_only)
        self.assertEqual(keypair.pubkey, keypair_pub.pubkey)

        # Test get_key privkey
        keypair_priv = self.ks.get_key(fingerprint_priv)
        self.assertEqual(keypairs.EncryptingKeypair, type(keypair_priv))
        self.assertFalse(keypair_priv.public_only)
        self.assertEqual(keypair.privkey, keypair_priv.privkey)
        self.assertIsNotNone(keypair_priv.pubkey)
        self.assertEqual(keypair.pubkey, keypair_priv.pubkey)

        # Test del_key pubkey
        self.ks.del_key(fingerprint_pub)
        key = self.ks.get_key(fingerprint_pub)
        self.assertIsNone(key)

        # Test del_key privkey
        self.ks.del_key(fingerprint_priv)
        key = self.ks.get_key(fingerprint_priv)
        self.assertIsNone(key)
