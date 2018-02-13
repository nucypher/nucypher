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
        return API.ecdsa_verify(message, self._der_encoded_bytes(), pubkey)

    @classmethod
    def from_bytes(cls, signature_as_bytes, der_encoded=False):
        if der_encoded:
            r, s = decode_dss_signature(signature_as_bytes)
        else:
            if not len(signature_as_bytes) == 64:
                raise ValueError("Looking for exactly 64 bytes if you call from_bytes with der_encoded=False.")
            else:
                r = int.from_bytes(signature_as_bytes[:32], "big")
                s = int.from_bytes(signature_as_bytes[32:], "big")
        return cls(r, s)

    def _der_encoded_bytes(self):
        return encode_dss_signature(self.r, self.s)

    def __bytes__(self):
        return self.r.to_bytes(32, "big") + self.s.to_bytes(32, "big")

    def __len__(self):
        return len(bytes(self))

    def __add__(self, other):
        return bytes(self) + other

    def __radd__(self, other):
        return other + bytes(self)

    def __eq__(self, other):
        # TODO: Consider constant time
        return bytes(self) == bytes(other) or self._der_encoded_bytes() == other
