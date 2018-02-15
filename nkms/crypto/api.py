from random import SystemRandom
from typing import Tuple, Union

import sha3
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.exceptions import InvalidSignature
from py_ecc.secp256k1 import ecdsa_raw_recover

from umbral.keys import UmbralPrivateKey, UmbralPublicKey


SYSTEM_RAND = SystemRandom()


def secure_random(num_bytes: int) -> bytes:
    """
    Returns an amount `num_bytes` of data from the OS's random device.
    If a randomness source isn't found, returns a `NotImplementedError`.
    In this case, a secure random source most likely doesn't exist and
    randomness will have to found elsewhere.

    :param num_bytes: Number of bytes to return.

    :return: bytes
    """
    # TODO: Should we just use os.urandom or avoid the import w/ this?
    return SYSTEM_RAND.getrandbits(num_bytes * 8).to_bytes(num_bytes, byteorder='big')


def secure_random_range(min: int, max: int) -> int:
    """
    Returns a number from a secure random source betwee the range of
    `min` and `max` - 1.

    :param min: Minimum number in the range
    :param max: Maximum number in the range

    :return: int
    """
    return SYSTEM_RAND.randrange(min, max)


def keccak_digest(*messages: bytes) -> bytes:
    """
    Accepts an iterable containing bytes and digests it returning a
    Keccak digest of 32 bytes (keccak_256).

    :param bytes *messages: Data to hash

    :rtype: bytes
    :return: bytestring of digested data
    """
    hash = sha3.keccak_256()
    for message in messages:
        hash.update(message)
    return hash.digest()


def ecdsa_sign(message: bytes, privkey: UmbralPrivateKey) -> bytes:
    """
    Accepts a hashed message and signs it with the private key given.

    :param message: Message to hash and sign
    :param privkey: Private key to sign with

    :return: signature
    """
    cryptography_priv_key = privkey.bn_key.to_cryptography_priv_key()
    signature_der_bytes = cryptography_priv_key.sign(message, ec.ECDSA(hashes.BLAKE2b(64)))
    return signature_der_bytes


def ecdsa_verify(
        message: bytes,
        signature: bytes,
        pubkey: UmbralPublicKey
) -> bool:
    """
    Accepts a message and signature and verifies it with the
    provided public key.

    :param message: Message to verify
    :param signature: Signature to verify
    :param pubkey: UmbralPublicKey to verify signature with

    :return: True if valid, False if invalid.
    """
    cryptography_pub_key = pubkey.point_key.to_cryptography_pub_key()

    try:
        cryptography_pub_key.verify(
            signature,
            message,
            ec.ECDSA(hashes.BLAKE2b(64))
        )
    except InvalidSignature:
        return False
    return True
