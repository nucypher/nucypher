from nkms.crypto import api as API
from umbral.keys import UmbralPublicKey
from cryptography.hazmat.primitives.asymmetric.utils import decode_dss_signature, encode_dss_signature
from nkms.crypto.api import keccak_digest
from bytestring_splitter import BytestringSplitter


class Signature(object):
    """
    The Signature object allows signatures to be made and verified.
    """
    _EXPECTED_LENGTH = 64  # With secp256k1

    def __init__(self, r: int, s: int):
        #  TODO: Sanity check for proper r and s.
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
        # TODO: Change the int literals to variables which account for the order of the curve.
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


signature_splitter = BytestringSplitter(Signature)


class SignatureStamp(object):
    """
    Can be called to sign something or used to express the signing public
    key as bytes.
    """

    def __init__(self, character):
        self.character = character

    def __call__(self, *args, **kwargs):
        return self.character.sign(*args, **kwargs)

    def __bytes__(self):
        from nkms.crypto.powers import SigningPower
        return bytes(self.character.public_key(SigningPower))

    def __hash__(self):
        return int.from_bytes(self, byteorder="big")

    def __eq__(self, other):
        return other == bytes(self)

    def __add__(self, other):
        return bytes(self) + other

    def __radd__(self, other):
        return other + bytes(self)

    def __len__(self):
        return len(bytes(self))

    def as_umbral_pubkey(self):
        from nkms.crypto.powers import SigningPower
        return self.character.public_key(SigningPower)

    def fingerprint(self):
        """
        Hashes the key using keccak-256 and returns the hexdigest in bytes.

        :return: Hexdigest fingerprint of key (keccak-256) in bytes
        """
        return keccak_digest(bytes(self)).hex().encode()


class StrangerStamp(SignatureStamp):
    """
    SignatureStamp of a stranger (ie, can only be used to glean public key, not to sign)
    """

    def __call__(self, *args, **kwargs):
        message = "This isn't your SignatureStamp; it belongs to {} (a Stranger).  You can't sign with it."
        raise TypeError(message.format(self.character))
