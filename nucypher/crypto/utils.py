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

from coincurve import PublicKey
from eth_keys import KeyAPI as EthKeyAPI
from typing import Any
from umbral.keys import UmbralPublicKey
from umbral.signing import Signature

from nucypher.crypto.api import keccak_digest


def fingerprint_from_key(public_key: Any):
    """
    Hashes a key using keccak-256 and returns the hexdigest in bytes.
    :return: Hexdigest fingerprint of key (keccak-256) in bytes
    """
    return keccak_digest(bytes(public_key)).hex().encode()


def construct_policy_id(label: bytes, stamp: bytes) -> bytes:
    """
    Forms an ID unique to the policy per label and Bob's signing pubkey via
    a keccak hash of the two.
    """
    return keccak_digest(label + stamp)


def canonical_address_from_umbral_key(public_key: UmbralPublicKey) -> bytes:
    pubkey_raw_bytes = public_key.to_bytes(is_compressed=False)[1:]
    eth_pubkey = EthKeyAPI.PublicKey(pubkey_raw_bytes)
    canonical_address = eth_pubkey.to_canonical_address()
    return canonical_address


def recover_pubkey_from_signature(prehashed_message, signature, v_value_to_try=None) -> bytes:
    """
    Recovers a serialized, compressed public key from a signature.
    It allows to specify a potential v value, in which case it assumes the signature
    has the traditional (r,s) raw format. If a v value is not present, it assumes
    the signature has the recoverable format (r, s, v).

    :param prehashed_message: Prehashed message
    :param signature: The signature from which the pubkey is recovered
    :param v_value_to_try: A potential v value to try
    :return: The compressed byte-serialized representation of the recovered public key
    """

    signature = bytes(signature)
    ecdsa_signature_size = Signature.expected_bytes_length()

    if not v_value_to_try:
        expected_signature_size = ecdsa_signature_size + 1
        if not len(signature) == expected_signature_size:
            raise ValueError(f"When not passing a v value, "
                             f"the signature size should be {expected_signature_size} B.")
    elif v_value_to_try in (0, 1, 27, 28):
        expected_signature_size = ecdsa_signature_size
        if not len(signature) == expected_signature_size:
            raise ValueError(f"When passing a v value, "
                             f"the signature size should be {expected_signature_size} B.")
        if v_value_to_try >= 27:
            v_value_to_try -= 27
        signature = signature + v_value_to_try.to_bytes(1, 'big')
    else:
        raise ValueError("Wrong v value. It should be 0, 1, 27 or 28.")

    pubkey = PublicKey.from_signature_and_message(serialized_sig=signature,
                                                  message=prehashed_message,
                                                  hasher=None)
    return pubkey.format(compressed=True)
