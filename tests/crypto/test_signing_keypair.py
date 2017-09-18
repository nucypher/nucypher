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
            msgpack.loads(signature)
        except Exception as e:
            self.fail("Failed to msgpack.load signature: {}".format(e))
