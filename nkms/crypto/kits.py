from constant_sorrow import constants, default_constant_splitter
from crypto_kits.kits import MessageKit
from umbral import pre
from nkms.crypto.splitters import key_splitter, capsule_splitter


class UmbralMessageKit(MessageKit):
    splitter = capsule_splitter + key_splitter
    _capsule = None
    _ciphertext = None

    def decrypt(self, privkey):
        return pre.decrypt(
            self.capsule,
            self.ciphertext,
            self.alice_pubkey
        )


class AdventureKit(UmbralMessageKit):

    def later__init__(self, ciphertext, capsule, treasure_map, alice_pubkey=None):
        super().__init__(ciphertext, capsule, alice_pubkey)
        self.treasure_map = treasure_map
