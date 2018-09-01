from typing import Any

from nucypher.crypto.api import keccak_digest


def fingerprint_from_key(public_key: Any):
    """
    Hashes a key using keccak-256 and returns the hexdigest in bytes.
    :return: Hexdigest fingerprint of key (keccak-256) in bytes
    """
    return keccak_digest(bytes(public_key)).hex().encode()
