from secrets import SystemRandom
from typing import Union

from eth_account.account import Account
from eth_account.messages import encode_defunct
from eth_hash.auto import keccak
from eth_keys import KeyAPI as EthKeyAPI
from eth_utils.address import to_checksum_address
from nucypher_core.umbral import PublicKey

from nucypher.crypto.signing import SignatureStamp

SYSTEM_RAND = SystemRandom()


def canonical_address_from_umbral_key(public_key: Union[PublicKey, SignatureStamp]) -> bytes:
    if isinstance(public_key, SignatureStamp):
        public_key = public_key.as_umbral_pubkey()
    pubkey_compressed_bytes = public_key.to_compressed_bytes()
    eth_pubkey = EthKeyAPI.PublicKey.from_compressed_bytes(pubkey_compressed_bytes)
    canonical_address = eth_pubkey.to_canonical_address()
    return canonical_address


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
    Returns a number from a secure random source between the range of
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

    Uses `eth_hash`, which accepts bytearray/bytes only, to provide a consistent implementation.

    Although we use SHA256 in many cases, we keep keccak handy in order
    to provide compatibility with the Ethereum blockchain.

    :param bytes: Data to hash

    :rtype: bytes
    :return: bytestring of digested data
    """
    # TODO: There's a higher-level tool in eth-utils that will optionally also take a string.  Do we want to use that?
    # https://eth-utils.readthedocs.io/en/stable/utilities.html#keccak-bytes-int-bool-text-str-hexstr-str-bytes
    joined_bytes = bytes().join(messages)
    digest = keccak(joined_bytes)
    return digest


def recover_address_eip_191(message: bytes, signature: bytes) -> str:
    """
    Recover checksum address from EIP-191 signature
    """
    signable_message = encode_defunct(primitive=message)
    recovery = Account.recover_message(signable_message=signable_message, signature=signature)
    recovered_address = to_checksum_address(recovery)
    return recovered_address


def verify_eip_191(address: str, message: bytes, signature: bytes) -> bool:
    """
    EIP-191 Compatible signature verification for usage with w3.eth.sign.
    """
    recovered_address = recover_address_eip_191(message=message, signature=signature)
    signature_is_valid = recovered_address == to_checksum_address(address)
    return signature_is_valid
