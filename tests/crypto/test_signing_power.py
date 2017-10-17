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

        sig = API.ecdsa_load_sig(sig)
        self.assertEqual(tuple, type(sig))
        self.assertEqual(3, len(sig))
        self.assertEqual(int, type(sig[0]))
        self.assertEqual(int, type(sig[1]))
        self.assertEqual(int, type(sig[2]))

        v, r, s = sig
        is_verify = API.ecdsa_verify(v, r, s, msghash, self.keypair.pubkey)
        self.assertTrue(is_verify)
