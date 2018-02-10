import unittest
from nkms.crypto import api as API
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
        self.assertEqual(PublicKey._EXPECTED_LENGTH, len(self.ecdsa_keypair.pubkey))

    def test_ecdsa_keypair_signing(self):
        msghash = API.keccak_digest(b'hello world!')

        sig = self.ecdsa_keypair.sign(msghash)
        self.assertEqual(bytes, type(sig))
        self.assertEqual(65, len(sig))

    def test_key_serialization(self):
        ser_key = self.ecdsa_keypair.serialize_privkey()
        self.assertEqual(34, len(ser_key))

        deser_key = keypairs.Keypair.deserialize_key(ser_key)
        self.assertEqual(keypairs.SigningKeypair, type(deser_key))
        self.assertEqual(self.ecdsa_keypair.privkey, deser_key.privkey)

    def test_ecdsa_keypair_verification(self):
        msghash = API.keccak_digest(b'hello world!')

        sig = self.ecdsa_keypair.sign(msghash)
        self.assertEqual(bytes, type(sig))
        self.assertEqual(65, len(sig))

        is_valid = self.ecdsa_keypair.verify(msghash, sig)
        self.assertTrue(is_valid)

    def test_keypair_object(self):
        # Test both keys
        keypair = keypairs.SigningKeypair(self.ecdsa_keypair.privkey,
                                          self.ecdsa_keypair.pubkey)
        self.assertTrue(keypair.public_only is False)

        self.assertEqual(bytes, type(keypair.privkey))
        self.assertEqual(32, len(keypair.privkey))

        self.assertEqual(PublicKey._EXPECTED_LENGTH, len(keypair.pubkey))

        # Test no keys (key generation)
        keypair = keypairs.SigningKeypair()
        self.assertTrue(keypair.public_only is False)

        self.assertEqual(bytes, type(keypair.privkey))
        self.assertEqual(32, len(keypair.privkey))

        self.assertEqual(PublicKey._EXPECTED_LENGTH, len(keypair.pubkey))

        # Test privkey only
        keypair = keypairs.SigningKeypair(privkey=self.ecdsa_keypair.privkey)
        self.assertTrue(keypair.public_only is False)

        self.assertEqual(bytes, type(keypair.privkey))
        self.assertEqual(32, len(keypair.privkey))
        self.assertEqual(PublicKey._EXPECTED_LENGTH, len(keypair.pubkey))

        # Test pubkey only
        keypair = keypairs.SigningKeypair(pubkey=self.ecdsa_keypair.pubkey)
        self.assertTrue(keypair.public_only is True)

        self.assertEqual(PublicKey._EXPECTED_LENGTH, len(keypair.pubkey))
