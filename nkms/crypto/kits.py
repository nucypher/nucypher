from umbral import umbral


class MessageKit:

    def __init__(self, ciphertext, capsule, alice_pubkey=None):
        self.ciphertext = ciphertext
        self.capsule = capsule
        self.alice_pub_key = alice_pubkey

    def decrypt(self, privkey):
        return umbral.decrypt(
            self.capsule,
            self.ciphertext,
            self.alice_pubkey
        )


class MapKit(MessageKit):

    def __init__(self, ciphertext, capsule, treasure_map, alice_pubkey=None):
        super().__init__(ciphertext, capsule, alice_pubkey)
        self.treasure_map = treasure_map