from nkms.crypto import api as API
from umbral.keys import UmbralPublicKey


class Signature(bytes):
    """
    The Signature object allows signatures to be made and verified.
    """
    _EXPECTED_LENGTH = 70

    def __init__(self, sig_as_bytes: bytes):
        """
        Initializes a Signature object.
        :param sig_as_bytes: Cryptography.io signature as bytes.
        :return: Signature object
        """
        self.sig_as_bytes = sig_as_bytes

    def __repr__(self):
        return "ECDSA Signature: {}".format(sig_as_bytes.decode())

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
