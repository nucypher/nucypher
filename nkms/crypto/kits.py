from nkms.crypto.splitters import key_splitter, capsule_splitter
from constant_sorrow import constants


class CryptoKit:
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

    def __init__(self, capsule, sender_pubkey_sig=None, ciphertext=None, signature=constants.NOT_SIGNED):
        self.ciphertext = ciphertext
        self.capsule = capsule
        self.sender_pubkey_sig = sender_pubkey_sig
        self._signature = signature

    def to_bytes(self, include_alice_pubkey=True):
        # We include the capsule first.
        as_bytes = bytes(self.capsule)

        # Then, before the ciphertext, we see if we're including alice's public key.
        # We want to put that first because it's typically of known length.
        if include_alice_pubkey and self.sender_pubkey_sig:
            as_bytes += bytes(self.sender_pubkey_sig)

        as_bytes += self.ciphertext
        return as_bytes

    @property
    def signature(self):
        return self._signature

    def __bytes__(self):
        return bytes(self.capsule) + self.ciphertext


class UmbralMessageKit(MessageKit):
    return_remainder_when_splitting = True
    splitter = capsule_splitter + key_splitter

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.policy_pubkey = None

    @classmethod
    def from_bytes(cls, some_bytes):
        capsule, sender_pubkey_sig, ciphertext = cls.split_bytes(some_bytes)
        return cls(capsule=capsule, sender_pubkey_sig=sender_pubkey_sig, ciphertext=ciphertext)
