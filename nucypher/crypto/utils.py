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

from secrets import SystemRandom
from typing import Union, Tuple

import sha3
from constant_sorrow import constants
from cryptography.hazmat.backends.openssl.backend import backend
from cryptography.hazmat.primitives import hashes
from eth_account.account import Account
from eth_account.messages import encode_defunct
from eth_keys import KeyAPI as EthKeyAPI
from eth_utils.address import to_checksum_address

import nucypher.crypto.umbral_adapter as umbral
from nucypher.crypto.kits import UmbralMessageKit
from nucypher.crypto.signing import SignatureStamp
from nucypher.crypto.umbral_adapter import Signature, PublicKey

SYSTEM_RAND = SystemRandom()


def construct_policy_id(label: bytes, stamp: bytes) -> bytes:
    """
    Forms an ID unique to the policy per label and Bob's signing pubkey via
    a keccak hash of the two.
    """
    return keccak_digest(label + stamp)


def canonical_address_from_umbral_key(public_key: Union[PublicKey, SignatureStamp]) -> bytes:
    if isinstance(public_key, SignatureStamp):
        public_key = public_key.as_umbral_pubkey()
    pubkey_compressed_bytes = bytes(public_key)
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

    Although we use SHA256 in many cases, we keep keccak handy in order
    to provide compatibility with the Ethereum blockchain.

    :param bytes: Data to hash

    :rtype: bytes
    :return: bytestring of digested data
    """
    _hash = sha3.keccak_256()
    for message in messages:
        _hash.update(bytes(message))
    digest = _hash.digest()
    return digest


def sha256_digest(*messages: bytes) -> bytes:
    """
    Accepts an iterable containing bytes and digests it returning a
    SHA256 digest of 32 bytes

    :param bytes: Data to hash

    :rtype: bytes
    :return: bytestring of digested data
    """
    _hash_ctx = hashes.Hash(hashes.SHA256(), backend=backend)
    for message in messages:
        _hash_ctx.update(bytes(message))
    digest = _hash_ctx.finalize()
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


def encrypt_and_sign(recipient_pubkey_enc: PublicKey,
                     plaintext: bytes,
                     signer: 'SignatureStamp',
                     sign_plaintext: bool = True
                     ) -> Tuple[UmbralMessageKit, Signature]:
    if signer is not constants.DO_NOT_SIGN:
        # The caller didn't expressly tell us not to sign; we'll sign.
        if sign_plaintext:
            # Sign first, encrypt second.
            sig_header = constants.SIGNATURE_TO_FOLLOW
            signature = signer(plaintext)
            capsule, ciphertext = umbral.encrypt(recipient_pubkey_enc, sig_header + bytes(signature) + plaintext)
        else:
            # Encrypt first, sign second.
            sig_header = constants.SIGNATURE_IS_ON_CIPHERTEXT
            capsule, ciphertext = umbral.encrypt(recipient_pubkey_enc, sig_header + plaintext)
            signature = signer(ciphertext)
        message_kit = UmbralMessageKit(ciphertext=ciphertext, capsule=capsule,
                                       sender_verifying_key=signer.as_umbral_pubkey(),
                                       signature=signature)
    else:
        # Don't sign.
        signature = sig_header = constants.NOT_SIGNED
        capsule, ciphertext = umbral.encrypt(recipient_pubkey_enc, sig_header + plaintext)
        message_kit = UmbralMessageKit(ciphertext=ciphertext, capsule=capsule)

    return message_kit, signature
