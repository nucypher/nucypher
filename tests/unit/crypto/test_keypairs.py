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

import sha3
from constant_sorrow.constants import PUBLIC_ONLY

from nucypher.crypto import keypairs
from nucypher.crypto.umbral_adapter import SecretKey


def test_gen_keypair_if_needed():
    new_dec_keypair = keypairs.DecryptingKeypair()
    assert new_dec_keypair._privkey is not None
    assert new_dec_keypair.pubkey is not None
    assert new_dec_keypair.pubkey == new_dec_keypair._privkey.public_key()

    new_sig_keypair = keypairs.SigningKeypair()
    assert new_sig_keypair._privkey is not None
    assert new_sig_keypair.pubkey is not None
    assert new_sig_keypair.pubkey == new_sig_keypair._privkey.public_key()


def test_keypair_with_umbral_keys():
    umbral_privkey = SecretKey.random()
    umbral_pubkey = umbral_privkey.public_key()

    new_keypair_from_priv = keypairs.Keypair(umbral_privkey)
    assert new_keypair_from_priv._privkey == umbral_privkey
    assert bytes(new_keypair_from_priv.pubkey) == bytes(umbral_pubkey)

    new_keypair_from_pub = keypairs.Keypair(public_key=umbral_pubkey)
    assert bytes(new_keypair_from_pub.pubkey) == bytes(umbral_pubkey)
    assert new_keypair_from_pub._privkey == PUBLIC_ONLY


def test_keypair_serialization():
    umbral_pubkey = SecretKey.random().public_key()
    new_keypair = keypairs.Keypair(public_key=umbral_pubkey)

    pubkey_bytes = bytes(new_keypair.pubkey)
    assert pubkey_bytes == bytes(umbral_pubkey)


def test_keypair_fingerprint():
    umbral_pubkey = SecretKey.random().public_key()
    new_keypair = keypairs.Keypair(public_key=umbral_pubkey)

    fingerprint = new_keypair.fingerprint()
    assert fingerprint is not None

    umbral_fingerprint = sha3.keccak_256(bytes(umbral_pubkey)).hexdigest().encode()
    assert fingerprint == umbral_fingerprint


def test_signing():
    umbral_privkey = SecretKey.random()
    sig_keypair = keypairs.SigningKeypair(umbral_privkey)

    msg = b'peace at dawn'
    signature = sig_keypair.sign(msg)
    assert signature.verify(sig_keypair.pubkey, msg)

    bad_msg = b'bad message'
    assert not signature.verify(sig_keypair.pubkey, bad_msg)


# TODO: Add test for DecryptingKeypair.decrypt
