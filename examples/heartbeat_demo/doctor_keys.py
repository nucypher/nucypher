"""
 This file is part of nucypher.

 nucypher is free software: you can redistribute it and/or modify
 it under the terms of the GNU Affero General Public License as published by
 the Free Software Foundation, either version 3 of the License, or
 (at your option) any later version.

 nucypher is distributed in the hope that it will be useful,
 but WITHOUT ANY WARRANTY; without even the implied warranty of
 MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
 GNU Affero General Public License for more details.

 You should have received a copy of the GNU Affero General Public License
 along with nucypher.  If not, see <https://www.gnu.org/licenses/>.
"""

import json
from pathlib import Path

from nucypher.crypto.umbral_adapter import SecretKey, PublicKey

DOCTOR_PUBLIC_JSON = Path('doctor.public.json')
DOCTOR_PRIVATE_JSON = Path('doctor.private.json')


def generate_doctor_keys():
    enc_privkey = SecretKey.random()
    sig_privkey = SecretKey.random()

    doctor_privkeys = {
        'enc': enc_privkey.to_secret_bytes().hex(),
        'sig': sig_privkey.to_secret_bytes().hex(),
    }

    with open(DOCTOR_PRIVATE_JSON, 'w') as f:
        json.dump(doctor_privkeys, f)

    enc_pubkey = enc_privkey.public_key()
    sig_pubkey = sig_privkey.public_key()
    doctor_pubkeys = {
        'enc': bytes(enc_pubkey).hex(),
        'sig': bytes(sig_pubkey).hex()
    }
    with open(DOCTOR_PUBLIC_JSON, 'w') as f:
        json.dump(doctor_pubkeys, f)


def _get_keys(file, key_class):
    if not file.exists():
        generate_doctor_keys()

    with open(file) as f:
        stored_keys = json.load(f)
    keys = dict()
    for key_type, key_str in stored_keys.items():
        keys[key_type] = key_class.from_bytes(bytes.fromhex(key_str))
    return keys


def get_doctor_pubkeys():
    return _get_keys(DOCTOR_PUBLIC_JSON, PublicKey)


def get_doctor_privkeys():
    return _get_keys(DOCTOR_PRIVATE_JSON, SecretKey)
