import unittest
import sha3
from sqlalchemy import create_engine
from nkms.keystore.db import Base
from nkms.keystore import keystore, keypairs
from npre.umbral import RekeyFrag
from nkms.crypto import api as API


class TestKeyStore(unittest.TestCase):
    def setUp(self):
        engine = create_engine('sqlite:///:memory:')
        Base.metadata.create_all(engine)

        self.ks = keystore.KeyStore(engine)

    def test_ecies_keypair_generation(self):
        keypair = self.ks.generate_encrypting_keypair()
        self.assertEqual(keypairs.EncryptingKeypair, type(keypair))
        self.assertEqual(bytes, type(keypair.privkey))
        self.assertEqual(bytes, type(keypair.pubkey))

    def test_ecdsa_keypair_generation(self):
        keypair = self.ks.generate_signing_keypair()
        self.assertEqual(keypairs.SigningKeypair, type(keypair))
        self.assertEqual(bytes, type(keypair.privkey))
        self.assertEqual(bytes, type(keypair.pubkey))

    def test_key_sqlite_keystore(self):
        keypair = self.ks.generate_encrypting_keypair()
        self.assertEqual(keypairs.EncryptingKeypair, type(keypair))
        self.assertEqual(bytes, type(keypair.privkey))
        self.assertEqual(bytes, type(keypair.pubkey))

        # Test add pubkey
        fingerprint_pub = self.ks.add_key(keypair, store_pub=True)
        self.assertEqual(bytes, type(fingerprint_pub))
        self.assertEqual(64, len(fingerprint_pub))

        key_hash = sha3.keccak_256(keypair.pubkey).hexdigest().encode()
        self.assertEqual(key_hash, fingerprint_pub)

        # Test add privkey
        fingerprint_priv = self.ks.add_key(keypair, store_pub=False)
        self.assertEqual(bytes, type(fingerprint_priv))
        self.assertEqual(64, len(fingerprint_priv))

        key_hash = sha3.keccak_256(keypair.privkey).hexdigest().encode()
        self.assertEqual(key_hash, fingerprint_priv)

        # Test get pubkey
        keypair_pub = self.ks.get_key(fingerprint_pub)
        self.assertEqual(keypairs.EncryptingKeypair, type(keypair_pub))
        self.assertTrue(keypair_pub.public_only)
        self.assertEqual(keypair.pubkey, keypair_pub.pubkey)

        # Test get privkey
        keypair_priv = self.ks.get_key(fingerprint_priv)
        self.assertEqual(keypairs.EncryptingKeypair, type(keypair_priv))
        self.assertFalse(keypair_priv.public_only)
        self.assertEqual(keypair.privkey, keypair_priv.privkey)
        self.assertIsNotNone(keypair_priv.pubkey)
        self.assertEqual(keypair.pubkey, keypair_priv.pubkey)

        # Test del pubkey
        self.ks.del_key(fingerprint_pub)
        with self.assertRaises(keystore.KeyNotFound):
            key = self.ks.get_key(fingerprint_pub)

        # Test del privkey
        self.ks.del_key(fingerprint_priv)
        with self.assertRaises(keystore.KeyNotFound):
            key = self.ks.get_key(fingerprint_priv)

    def test_keyfrag_sqlite(self):
        rand_sig = API.secure_random(65)
        rand_id = API.secure_random(32)
        rand_key = API.secure_random(32)
        rand_hrac = API.secure_random(32)

        kfrag = RekeyFrag(id=rand_id, key=rand_key)
        self.ks.add_kfrag(rand_hrac, kfrag, sig=rand_sig)

        # Check that kfrag was added
        kfrag, signature = self.ks.get_kfrag(rand_hrac, get_sig=True)
        self.assertEqual(rand_sig, signature)
        self.assertEqual(kfrag.id, rand_id)
        self.assertEqual(kfrag.key, rand_key)

        # Check that kfrag gets deleted
        self.ks.del_kfrag(rand_hrac)
        with self.assertRaises(keystore.KeyNotFound):
            key = self.ks.get_key(rand_hrac)
