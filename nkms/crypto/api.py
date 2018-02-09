from random import SystemRandom
from typing import Tuple, Union

import sha3
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec
from py_ecc.secp256k1 import ecdsa_raw_recover

import umbral
from nkms.crypto.signature import Signature

SYSTEM_RAND = SystemRandom()


def secure_random(
        num_bytes: int
) -> bytes:
    """
    Returns an amount `num_bytes` of data from the OS's random device.
    If a randomness source isn't found, returns a `NotImplementedError`.
    In this case, a secure random source most likely doesn't exist and
    randomness will have to found elsewhere.

    :param num_bytes: Number of bytes to return.

    :return: bytes
    """
    # TODO: Should we just use os.urandom or avoid the import w/ this?
    return SYSTEM_RAND.getrandbits(num_bytes * 8).to_bytes(num_bytes,
                                                           byteorder='big')


def secure_random_range(
        min: int,
        max: int
) -> int:
    """
    Returns a number from a secure random source betwee the range of
    `min` and `max` - 1.

    :param min: Minimum number in the range
    :param max: Maximum number in the range

    :return: int
    """
    return SYSTEM_RAND.randrange(min, max)


def keccak_digest(
        *messages: bytes
) -> bytes:
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


def ecdsa_pub2bytes(
        pubkey: Tuple[int, int]
) -> bytes:
    """
    Takes an ECDSA public key and converts to bytes.

    :param pubkey: Tuple[int] of Public Key

    :return: bytestring of Public key
    """
    x = pubkey[0].to_bytes(32, byteorder='big')
    y = pubkey[1].to_bytes(32, byteorder='big')
    return x + y


def ecdsa_bytes2pub(
        pubkey: bytes
) -> Tuple[int, int]:
    """
    Takes a byte encoded ECDSA public key and converts to a Tuple of x, and y

    :param pubkey: Byte encoded public key

    :return: Tuple[int] of Public Key
    """
    x = int.from_bytes(pubkey[:32], byteorder='big')
    y = int.from_bytes(pubkey[32:], byteorder='big')
    return (x, y)


def ecdsa_gen_sig(
        v: int,
        r: int,
        s: int
) -> bytes:
    """
    Generates an ECDSA signature, in bytes.

    :param v: v of sig
    :param r: r of sig
    :param s: s of sig

    :return: bytestring of v, r, and s
    """
    _v = v.to_bytes(1, byteorder='big')
    _r = r.to_bytes(32, byteorder='big')
    _s = s.to_bytes(32, byteorder='big')
    return _v + _r + _s


def ecdsa_load_sig(
        signature: bytes
) -> Tuple[int, int, int]:
    """
    Loads an ECDSA signature, from a bytestring, to a tuple.

    :param signature: Signature, as a bytestring, of v, r, and s.

    :return: Tuple(v, r, s)
    """
    v = int.from_bytes(signature[:1], byteorder='big')
    r = int.from_bytes(signature[1:33], byteorder='big')
    s = int.from_bytes(signature[33:], byteorder='big')
    return (v, r, s)


def ecdsa_sign(message: bytes, privkey: umbral.keys.UmbralPrivateKey) -> bytes:
    """
    Accepts a hashed message and signs it with the private key given.

    :param message: Message to hash and sign
    :param privkey: Private key to sign with

    :return: signature
    """
    cryptography_priv_key = privkey.bn_key.to_cryptography_priv_key()
    signature_bytes = cryptography_priv_key.sign(message, ec.ECDSA(hashes.BLAKE2b(64)))
    return Signature(signature_bytes)


def ecdsa_verify(
        v: int,
        r: int,
        s: int,
        msghash: bytes,
        pubkey: Union[bytes, Tuple[int, int]]
) -> bool:
    """
    Takes a v, r, s, a pubkey, and a hash of a message to verify via ECDSA.

    :param v: V of sig
    :param r: R of sig
    :param s: S of sig
    :param bytes msghash: The hashed message to verify
    :param bytes pubkey: Pubkey to validate signature for

    :rtype: Boolean
    :return: Is the signature valid or not?
    """
    if bytes == type(pubkey):
        pubkey = ecdsa_bytes2pub(pubkey)

    verify_sig = ecdsa_raw_recover(msghash, (v, r, s))
    # TODO: Should this equality test be done better?
    return verify_sig == pubkey
