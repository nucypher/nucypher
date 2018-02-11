from nkms.crypto import api as API
from umbral.keys import UmbralPublicKey
from cryptography.hazmat.primitives.asymmetric.utils import decode_dss_signature, encode_dss_signature


class Signature(object):
    """
    The Signature object allows signatures to be made and verified.
    """
    _EXPECTED_LENGTH = 64  # With secp256k1 and BLAKE2b(64).

    def __init__(self, r: int, s: int):
        self.r = r
        self.s = s

    def __repr__(self):
        return "ECDSA Signature: {}".format(bytes(self).hex()[:15])

    def verify(self, message: bytes, pubkey: UmbralPublicKey) -> bool:
        """
        Verifies that a message's signature was valid.

        :param message: The message to verify
        :param pubkey: UmbralPublicKey of the signer

        :return: True if valid, False if invalid
        """
        return API.ecdsa_verify(message, self.sig_as_bytes, pubkey)

    def __bytes__(self):
        """
        Implements the __bytes__ call for Signature to transform into a
        transportable mode.
        """
        return self.sig_as_bytes
