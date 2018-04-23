from nkms.crypto.api import encrypt_and_sign
from nkms.crypto.signature import SignatureStamp
from nkms.keystore.keypairs import SigningKeypair
from constant_sorrow.constants import NO_SIGNING_POWER
from umbral.keys import UmbralPublicKey


class DataSource:

    def __init__(self, policy_pubkey_enc, signer=NO_SIGNING_POWER, label=None):
        self.policy_pubkey = policy_pubkey_enc
        if signer is NO_SIGNING_POWER:
            signer = SignatureStamp(SigningKeypair())  # TODO: Generate signing key properly.  #241
        self.stamp = signer
        self.label = label

    def encapsulate_single_message(self, message):
        message_kit, signature = encrypt_and_sign(self.policy_pubkey,
                                                  plaintext=message,
                                                  signer=self.stamp)
        message_kit.policy_pubkey = self.policy_pubkey  # TODO: We can probably do better here.
        return message_kit, signature

    @classmethod
    def from_public_keys(cls, policy_public_key, datasource_public_key, label):
        umbral_public_key = UmbralPublicKey.from_bytes(datasource_public_key)
        return cls(policy_public_key,
                   signer=SignatureStamp(SigningKeypair(umbral_public_key)),
                   label=label,
                   )
