import json
import os
from umbral.keys import UmbralPrivateKey, UmbralPublicKey

ENCRYPTING_KEY = 'enc'
VERIFYING_KEY = 'sig'


class DemoKeyGenerator:
    def __init__(self,
                 storage_folder):
        self.recipient_public_json = storage_folder + '/recipient.{}.public.json'
        self.recipient_private_json = storage_folder + '/recipient.{}.private.json'

    def get_recipient_pubkeys(self, recipient_id: str):
        return self._get_keys(self.recipient_public_json.format(recipient_id), UmbralPublicKey, recipient_id)

    def get_recipient_privkeys(self, recipient_id: str):
        return self._get_keys(self.recipient_private_json.format(recipient_id), UmbralPrivateKey, recipient_id)

    def _generate_recipient_keys(self, recipient_id):
        self._generate_keys(self.recipient_private_json.format(recipient_id),
                            self.recipient_public_json.format(recipient_id))

    def _get_keys(self, file, key_class, recipient_id):
        if not os.path.isfile(file):
            self._generate_recipient_keys(recipient_id)

        with open(file) as f:
            stored_keys = json.load(f)
        keys = dict()
        for key_type, key_str in stored_keys.items():
            keys[key_type] = key_class.from_bytes(bytes.fromhex(key_str))
        return keys

    @staticmethod
    def _generate_keys(private_json_file: str, public_json_file: str):
        enc_privkey = UmbralPrivateKey.gen_key()
        sig_privkey = UmbralPrivateKey.gen_key()

        privkeys = {
            ENCRYPTING_KEY: enc_privkey.to_bytes().hex(),
            VERIFYING_KEY: sig_privkey.to_bytes().hex(),
        }

        with open(private_json_file, 'w') as f:
            json.dump(privkeys, f)

        enc_pubkey = enc_privkey.get_pubkey()
        sig_pubkey = sig_privkey.get_pubkey()
        pubkeys = {
            ENCRYPTING_KEY: enc_pubkey.to_bytes().hex(),
            VERIFYING_KEY: sig_pubkey.to_bytes().hex()
        }
        with open(public_json_file, 'w') as f:
            json.dump(pubkeys, f)


