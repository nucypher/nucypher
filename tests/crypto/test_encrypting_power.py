import unittest
from nkms.crypto.powers import EncryptingPower
from nkms.keystore.keypairs import EncryptingKeypair


class TestEncryptingPowers(unittest.TestCase):
    def setUp(self):
        self.enc_keypair = EncryptingKeypair()
        self.enc_keypair.gen_privkey()

        self.enc_power = EncryptingPower(self.enc_keypair)

    def test_encryption(self):
        data = b'hello world'

        enc_data = self.enc_power.encrypt(data)
        self.assertTrue(tuple, type(enc_data))
        self.assertEqual(2, len(enc_data))
        self.assertTrue(bytes, type(enc_data[0]))
        self.assertTrue(bytes, type(enc_data[1]))

        self.assertNotEqual(data, enc_data[0])

    def test_decryption(self):
        data = b'hello world'

        enc_data = self.enc_power.encrypt(data)
        self.assertTrue(tuple, type(enc_data))
        self.assertEqual(2, len(enc_data))
        self.assertTrue(bytes, type(enc_data[0]))
        self.assertTrue(bytes, type(enc_data[1]))
        self.assertNotEqual(data, enc_data[0])

        dec_data = self.enc_power.decrypt(enc_data)
        self.assertTrue(bytes, type(dec_data))
        self.assertEqual(data, dec_data)
