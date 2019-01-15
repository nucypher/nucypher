import json
import os
from umbral.keys import UmbralPrivateKey, UmbralPublicKey

KEYS_FOLDER = './keys'

ALICIA_PUBLIC_JSON = KEYS_FOLDER + '/alicia.public.json'
ALICIA_PRIVATE_JSON = KEYS_FOLDER + '/alicia.private.json'

RECIPIENT_PUBLIC_JSON = KEYS_FOLDER + '/recipient.{}.public.json'
RECIPIENT_PRIVATE_JSON = KEYS_FOLDER + '/recipient.{}.private.json'


def get_alicia_pubkeys():
    return _get_keys(ALICIA_PUBLIC_JSON, UmbralPublicKey)


def get_recipient_pubkeys(recipient_id: str = None):
    return _get_keys(RECIPIENT_PUBLIC_JSON.format(recipient_id), UmbralPublicKey, recipient_id)


def get_alicia_privkeys():
    return _get_keys(ALICIA_PRIVATE_JSON, UmbralPrivateKey)


def get_recipient_privkeys(recipient_id: str = None):
    return _get_keys(RECIPIENT_PRIVATE_JSON.format(recipient_id), UmbralPrivateKey, recipient_id)


def _generate_alicia_keys():
    _generate_keys(ALICIA_PRIVATE_JSON, ALICIA_PUBLIC_JSON)


def _generate_recipient_keys(recipient_id):
    _generate_keys(RECIPIENT_PRIVATE_JSON.format(recipient_id), RECIPIENT_PUBLIC_JSON.format(recipient_id))


def _generate_keys(private_json_file: str, public_json_file: str):
    enc_privkey = UmbralPrivateKey.gen_key()
    sig_privkey = UmbralPrivateKey.gen_key()

    privkeys = {
        'enc': enc_privkey.to_bytes().hex(),
        'sig': sig_privkey.to_bytes().hex(),
    }

    with open(private_json_file, 'w') as f:
        json.dump(privkeys, f)

    enc_pubkey = enc_privkey.get_pubkey()
    sig_pubkey = sig_privkey.get_pubkey()
    pubkeys = {
        'enc': enc_pubkey.to_bytes().hex(),
        'sig': sig_pubkey.to_bytes().hex()
    }
    with open(public_json_file, 'w') as f:
        json.dump(pubkeys, f)


def _get_keys(file, key_class, recipient_id: str = None):
    if not os.path.isfile(file):
        if file in (ALICIA_PUBLIC_JSON, ALICIA_PRIVATE_JSON):
            _generate_alicia_keys()
        else:
            _generate_recipient_keys(recipient_id)

    with open(file) as f:
        stored_keys = json.load(f)
    keys = dict()
    for key_type, key_str in stored_keys.items():
        keys[key_type] = key_class.from_bytes(bytes.fromhex(key_str))
    return keys
