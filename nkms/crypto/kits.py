from nkms.crypto.splitters import key_splitter, capsule_splitter
from constant_sorrow import constants


class CryptoKit:
    return_remainder_when_splitting = True
    splitter = None

    @classmethod
    def split_bytes(cls, some_bytes):
        if not cls.splitter:
            raise TypeError("This kit doesn't have a splitter defined.")

        return cls.splitter(some_bytes,
                            return_remainder=cls.return_remainder_when_splitting)

    @classmethod
    def from_bytes(cls, some_bytes):
        constituents = cls.split_bytes(some_bytes)
        return cls(*constituents)


class MessageKit(CryptoKit):

    _signature = constants.NOT_SIGNED

    def __init__(self, capsule, sender_pubkey=None, ciphertext=None):
        self.ciphertext = ciphertext
        self.capsule = capsule
        self.sender_pubkey = sender_pubkey

    def to_bytes(self, include_alice_pubkey=True):
        # We include the capsule first.
        as_bytes = bytes(self.capsule)

        # Then, before the ciphertext, we see if we're including alice's public key.
        # We want to put that first because it's typically of known length.
        if include_alice_pubkey and self.sender_pubkey:
            as_bytes += bytes(self.sender_pubkey)

        as_bytes += self.ciphertext
        return as_bytes

    @property
    def signature(self):
        return self._signature

    def __bytes__(self):
        return bytes(self.capsule) + self.ciphertext


class UmbralMessageKit(MessageKit):
    splitter = capsule_splitter + key_splitter
