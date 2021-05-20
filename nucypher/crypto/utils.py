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
from typing import Any, Union
from umbral.keys import UmbralPublicKey

from nucypher.crypto.api import keccak_digest
from nucypher.crypto.signing import SignatureStamp


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


def canonical_address_from_umbral_key(public_key: Union[UmbralPublicKey, SignatureStamp]) -> bytes:
    if isinstance(public_key, SignatureStamp):
        public_key = public_key.as_umbral_pubkey()
    pubkey_compressed_bytes = public_key.to_bytes(is_compressed=True)
    eth_pubkey = EthKeyAPI.PublicKey.from_compressed_bytes(pubkey_compressed_bytes)
    canonical_address = eth_pubkey.to_canonical_address()
    return canonical_address
