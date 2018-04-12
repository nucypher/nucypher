from nkms.crypto.api import encrypt_and_sign
from nkms.crypto.kits import MessageKit
from umbral import pre
from nkms.crypto.powers import EncryptingPower


class DataSource:

    def __init__(self, policy):
        self._policy_key = policy.alice.public_key(EncryptingPower)

    def encapsulate_single_message(self, message):
        encrypt_and_sign(self._policy_key, plaintext=message, signer=None)
        ciphertext, capsule = pre.encrypt(self._policy_key, message)
        return MessageKit(ciphertext=ciphertext,
                          capsule=capsule,
                          sender_pubkey=self._policy_key)
