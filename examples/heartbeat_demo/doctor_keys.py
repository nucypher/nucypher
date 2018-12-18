import json
import os
from umbral.keys import UmbralPrivateKey, UmbralPublicKey

DOCTOR_PUBLIC_JSON = 'doctor.public.json'
DOCTOR_PRIVATE_JSON = 'doctor.private.json'


def generate_doctor_keys():
    enc_privkey = UmbralPrivateKey.gen_key()
    sig_privkey = UmbralPrivateKey.gen_key()

    doctor_privkeys = {
        'enc': enc_privkey.to_bytes().hex(),
        'sig': sig_privkey.to_bytes().hex(),
    }

    with open(DOCTOR_PRIVATE_JSON, 'w') as f:
        json.dump(doctor_privkeys, f)

    enc_pubkey = enc_privkey.get_pubkey()
    sig_pubkey = sig_privkey.get_pubkey()
    doctor_pubkeys = {
        'enc': enc_pubkey.to_bytes().hex(),
        'sig': sig_pubkey.to_bytes().hex()
    }
    with open(DOCTOR_PUBLIC_JSON, 'w') as f:
        json.dump(doctor_pubkeys, f)


def _get_keys(file, key_class):
    if not os.path.isfile(file):
        generate_doctor_keys()

    with open(file) as f:
        stored_keys = json.load(f)
    keys = dict()
    for key_type, key_str in stored_keys.items():
        keys[key_type] = key_class.from_bytes(bytes.fromhex(key_str))
    return keys


def get_doctor_pubkeys():
    return _get_keys(DOCTOR_PUBLIC_JSON, UmbralPublicKey)


def get_doctor_privkeys():
    return _get_keys(DOCTOR_PRIVATE_JSON, UmbralPrivateKey)
