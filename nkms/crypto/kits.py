from nkms.crypto.splitters import key_splitter, capsule_splitter
from umbral import umbral


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

    def __init__(self, capsule, alice_pubkey, ciphertext):
        self.ciphertext = ciphertext
        self.capsule = capsule
        self.alice_pubkey = alice_pubkey

    def decrypt(self, privkey):
        return umbral.decrypt(
            self.capsule,
            self.ciphertext,
            self.alice_pubkey
        )

    def __bytes__(self):
        as_bytes = bytes(self.capsule)
        if self.alice_pubkey:
            as_bytes += bytes(self.alice_pubkey)
        as_bytes += self.ciphertext
        return as_bytes

class MapKit(MessageKit):

    def __init__(self, ciphertext, capsule, treasure_map, alice_pubkey=None):
        super().__init__(ciphertext, capsule, alice_pubkey)
        self.treasure_map = treasure_map