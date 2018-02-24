from nkms.crypto.splitters import key_splitter, capsule_splitter
from umbral import pre


class CryptoKit:
    return_remainder_when_splitting = True

    @classmethod
    def split_bytes(cls, some_bytes):
        return cls.splitter(some_bytes,
                            return_remainder=cls.return_remainder_when_splitting)

    @classmethod
    def from_bytes(cls, some_bytes):
        constituents = cls.split_bytes(some_bytes)
        return cls(*constituents)


class MessageKit(CryptoKit):
    splitter = capsule_splitter + key_splitter

    def __init__(self, capsule, alice_pubkey=None, ciphertext=None):
        self.ciphertext = ciphertext
        self.capsule = capsule
        self.alice_pubkey = alice_pubkey

    def decrypt(self, privkey):
        return pre.decrypt(
            self.capsule,
            self.ciphertext,
            self.alice_pubkey
        )

    def to_bytes(self, include_alice_pubkey=True):
        as_bytes = bytes(self.capsule)
        if include_alice_pubkey and self.alice_pubkey:
            as_bytes += bytes(self.alice_pubkey)
        as_bytes += self.ciphertext
        return as_bytes

    def __bytes__(self):
        return self.ciphertext

class MapKit(MessageKit):
    def __init__(self, ciphertext, capsule, treasure_map, alice_pubkey=None):
        super().__init__(ciphertext, capsule, alice_pubkey)
        self.treasure_map = treasure_map
