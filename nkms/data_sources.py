from nkms.crypto.api import encrypt_and_sign
from nkms.crypto.signature import SignatureStamp
from nkms.keystore.keypairs import SigningKeypair
from constant_sorrow.constants import NO_SIGNING_POWER

class DataSource:

    def __init__(self, policy_pubkey_enc, signer=NO_SIGNING_POWER):
        self._policy_pubkey_enc = policy_pubkey_enc
        if signer is NO_SIGNING_POWER:
            signer = SignatureStamp(SigningKeypair())  # TODO: Generate signing key properly.  #241
        self.stamp = signer

    def encapsulate_single_message(self, message):
        message_kit, signature = encrypt_and_sign(self._policy_pubkey_enc,
                                                  plaintext=message,
                                                  signer=self.stamp)
        message_kit.policy_pubkey = self._policy_pubkey_enc  # TODO: We can probably do better here.
        return message_kit, signature
