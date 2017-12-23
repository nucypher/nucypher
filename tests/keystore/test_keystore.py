import unittest
import sha3
from sqlalchemy import create_engine

from nkms.crypto.fragments import KFrag
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
        kfrag_component_length = 32
        rand_sig = API.secure_random(65)
        rand_id = b'\x00' + API.secure_random(kfrag_component_length)
        rand_key = b'\x00' + API.secure_random(kfrag_component_length)
        rand_hrac = API.secure_random(32)

        kfrag = KFrag(rand_id+rand_key)
        self.ks.add_kfrag(rand_hrac, kfrag, sig=rand_sig)

        # Check that kfrag was added
        kfrag_from_datastore, signature = self.ks.get_kfrag(rand_hrac, get_sig=True)
        self.assertEqual(rand_sig, signature)

        # De/serialization happens here, by dint of the slicing interface, which casts the kfrag to bytes.
        # The +1 is to account for the metabyte.
        self.assertEqual(kfrag_from_datastore[:kfrag_component_length + 1], rand_id)
        self.assertEqual(kfrag_from_datastore[kfrag_component_length + 1:], rand_key)
        self.assertEqual(kfrag_from_datastore, kfrag)

        # Check that kfrag gets deleted
        self.ks.del_kfrag(rand_hrac)
        with self.assertRaises(keystore.KeyNotFound):
            key = self.ks.get_key(rand_hrac)
