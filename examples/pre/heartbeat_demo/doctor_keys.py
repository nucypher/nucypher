import json
from pathlib import Path

from nucypher_core.umbral import PublicKey, SecretKey

DOCTOR_PUBLIC_JSON = Path("doctor.public.json")
DOCTOR_PRIVATE_JSON = Path("doctor.private.json")


def generate_doctor_keys():
    enc_privkey = SecretKey.random()
    sig_privkey = SecretKey.random()

    doctor_privkeys = {
        "enc": enc_privkey.to_be_bytes().hex(),
        "sig": sig_privkey.to_be_bytes().hex(),
    }

    with open(DOCTOR_PRIVATE_JSON, "w") as f:
        json.dump(doctor_privkeys, f)

    enc_pubkey = enc_privkey.public_key()
    sig_pubkey = sig_privkey.public_key()
    doctor_pubkeys = {
        "enc": enc_pubkey.to_compressed_bytes().hex(),
        "sig": sig_pubkey.to_compressed_bytes().hex(),
    }
    with open(DOCTOR_PUBLIC_JSON, "w") as f:
        json.dump(doctor_pubkeys, f)


def _get_keys(file, public=False):
    if not file.exists():
        generate_doctor_keys()

    with open(file) as f:
        stored_keys = json.load(f)
    keys = dict()
    for key_type, key_str in stored_keys.items():
        data = bytes.fromhex(key_str)
        if public:
            key = PublicKey.from_compressed_bytes(data)
        else:
            key = SecretKey.from_be_bytes(data)
        keys[key_type] = key
    return keys


def get_doctor_pubkeys():
    return _get_keys(DOCTOR_PUBLIC_JSON, public=True)


def get_doctor_privkeys():
    return _get_keys(DOCTOR_PRIVATE_JSON, public=False)
