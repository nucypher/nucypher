from nkms.crypto.api import encrypt_and_sign
from nkms.crypto.powers import DelegatingPower


class DataSource:

    def __init__(self, policy, signer):
        self._policy_key = policy.alice.public_key(DelegatingPower)
        self.stamp = signer

    def encapsulate_single_message(self, message):
        message_kit, signature = encrypt_and_sign(self._policy_key, plaintext=message, signer=self.stamp)
        message_kit.policy_pubkey = self._policy_key  # TODO: We can probably do better here.
        return message_kit, signature
