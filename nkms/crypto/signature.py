from umbral.keys import UmbralPublicKey

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec, utils
from cryptography.hazmat.backends import backend
from cryptography.exceptions import InvalidSignature


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
        return "{}".format(sig_as_bytes.decode())

    def verify(self, message: bytes, pubkey: UmbralPublicKey) -> bool:
        """
        Verifies that a message's signature was valid.

        :param message: The message to verify
        :param pubkey: UmbralPublicKey of the signer

        :return: True if valid, False if invalid
        """
        crypto_pubkey = pubkey.point_key.to_cryptography_pub_key()

        hasher = hashes.Hash(hashes.blake2b(), backend=backend)
        hasher.update(message)
        hash_digest = hasher.finalize()

        try:
            crypto_pubkey.verify(
                self.sig_as_bytes,
                hash_digest,
                ec.ECDSA(utils.Prehashed(hashes.blake2b()))
            )
        except InvalidSignature:
            return False
        else:
            return True

    def __bytes__(self):
        """
        Implements the __bytes__ call for Signature to transform into a
        transportable mode.
        """
        return sig_as_bytes
