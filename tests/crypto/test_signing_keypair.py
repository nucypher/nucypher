import unittest
import sha3
import msgpack
from nkms.crypto.keyring.keys import SigningKeypair


class TestSigningKeypair(unittest.TestCase):
    def setUp(self):
        self.keypair = SigningKeypair()
        self.msg = b'this is a test'

    def test_signing(self):
        msg_digest = sha3.keccak_256(self.msg).digest()
        signature = self.keypair.sign(msg_digest)

        try:
            sig = msgpack.loads(signature)
            self.assertTrue(1, len(sig[0]))     # Check v
            self.assertTrue(32, len(sig[1]))    # Check r
            self.assertTrue(32, len(sig[2]))    # Check s
        except Exception as e:
            self.fail("Failed to msgpack.load signature: {}".format(e))

    def test_verification(self):
        msg_digest = sha3.keccak_256(self.msg).digest()
        signature = self.keypair.sign(msg_digest)

        try:
            sig = msgpack.loads(signature)
            self.assertTrue(1, len(sig[0]))     # Check v
            self.assertTrue(32, len(sig[1]))    # Check r
            self.assertTrue(32, len(sig[2]))    # Check s
        except Exception as e:
            self.fail("Failed to msgpack.load signature: {}".format(e))

        verify_sig = self.keypair.verify(msg_digest, signature)
        self.assertTrue(verify_sig)
