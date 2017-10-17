import unittest
from nkms.keystore import keypairs
from nkms.crypto import api as API
from nkms.crypto.powers import SigningPower


class TestSigningPower(unittest.TestCase):
    def setUp(self):
        self.keypair = keypairs.SigningKeypair()
        self.power = SigningPower(self.keypair)

    def test_signing(self):
        msghash = API.keccak_digest(b'hello world!')

        sig = self.power.sign(msghash)
        self.assertEqual(bytes, type(sig))
        self.assertEqual(65, len(sig))

        is_valid = self.keypair.verify(msghash, sig)
        self.assertTrue(is_valid)
