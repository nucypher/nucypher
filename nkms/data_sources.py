from nkms.crypto.api import encrypt_and_sign


class DataSource:

    def __init__(self, policy_pubkey_enc, signer):
        self._policy_pubkey_enc = policy_pubkey_enc
        self.stamp = signer

    def encapsulate_single_message(self, message):
        message_kit, signature = encrypt_and_sign(self._policy_pubkey_enc,
                                                  plaintext=message,
                                                  signer=self.stamp)
        message_kit.policy_pubkey = self._policy_pubkey_enc  # TODO: We can probably do better here.
        return message_kit, signature
