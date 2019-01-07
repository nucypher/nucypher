import json
import os
from umbral.keys import UmbralPrivateKey, UmbralPublicKey

ALICIA_PUBLIC_JSON = 'alicia.public.json'
ALICIA_PRIVATE_JSON = 'alicia.private.json'

DOCTOR_PUBLIC_JSON = 'doctor.public.json'
DOCTOR_PRIVATE_JSON = 'doctor.private.json'


def get_alicia_pubkeys():
    return _get_keys(ALICIA_PUBLIC_JSON, UmbralPublicKey)


def get_doctor_pubkeys():
    return _get_keys(DOCTOR_PUBLIC_JSON, UmbralPublicKey)


def get_alicia_privkeys():
    return _get_keys(ALICIA_PRIVATE_JSON, UmbralPrivateKey)


def get_doctor_privkeys():
    return _get_keys(DOCTOR_PRIVATE_JSON, UmbralPrivateKey)


def _generate_alicia_keys():
    _generate_keys(ALICIA_PRIVATE_JSON, ALICIA_PUBLIC_JSON)


def _generate_doctor_keys():
    _generate_keys(DOCTOR_PRIVATE_JSON, DOCTOR_PUBLIC_JSON)


def _generate_keys(private_json: str, public_json: str):
    enc_privkey = UmbralPrivateKey.gen_key()
    sig_privkey = UmbralPrivateKey.gen_key()

    privkeys = {
        'enc': enc_privkey.to_bytes().hex(),
        'sig': sig_privkey.to_bytes().hex(),
    }

    with open(private_json, 'w') as f:
        json.dump(privkeys, f)

    enc_pubkey = enc_privkey.get_pubkey()
    sig_pubkey = sig_privkey.get_pubkey()
    pubkeys = {
        'enc': enc_pubkey.to_bytes().hex(),
        'sig': sig_pubkey.to_bytes().hex()
    }
    with open(public_json, 'w') as f:
        json.dump(pubkeys, f)


def _get_keys(file, key_class):
    if not os.path.isfile(file):
        if file in (DOCTOR_PUBLIC_JSON, DOCTOR_PRIVATE_JSON):
            _generate_doctor_keys()
        else:
            _generate_alicia_keys()

    with open(file) as f:
        stored_keys = json.load(f)
    keys = dict()
    for key_type, key_str in stored_keys.items():
        keys[key_type] = key_class.from_bytes(bytes.fromhex(key_str))
    return keys
