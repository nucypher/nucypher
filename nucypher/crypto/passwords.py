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


from cryptography.exceptions import InternalError
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from cryptography.hazmat.primitives.kdf.scrypt import Scrypt
from nacl.exceptions import CryptoError
from nacl.secret import SecretBox

from nucypher.crypto.constants import BLAKE2B

__MASTER_KEY_LENGTH = 32  # This will be passed to HKDF, but it is not picky about the length
__WRAPPING_KEY_LENGTH = SecretBox.KEY_SIZE
__WRAPPING_KEY_INFO = b'NuCypher-KeyWrap'
__HKDF_HASH_ALGORITHM = BLAKE2B


def derive_key_material_from_password(password: bytes, salt: bytes) -> bytes:
    """
    Derives a symmetric encryption key seed from a pair of password and salt.

    This is secure, but takes a long time.
    So only call it once, and use the resulting key material as a seed for specific keys
    (e.g by passing it to `derive_wrapping_key_from_key_material`, `secret_box_encrypt`
    or `secret_box_decrypt`)

    :param password: byte-encoded password used to derive a symmetric key
    :param salt: cryptographic salt added during key derivation
    :return:
    """

    # WARNING: RFC7914 recommends that you use a 2^20 cost value for sensitive
    # files. It is NOT recommended to change the `_scrypt_cost` value unless
    # you know what you are doing.
    _scrypt_cost = 20

    try:
        derived_key = Scrypt(
            salt=salt,
            length=__MASTER_KEY_LENGTH,
            n=2 ** _scrypt_cost,
            r=8,
            p=1,
            backend=default_backend()
        ).derive(password)
    except InternalError as e:
        required_memory = 128 * 2**_scrypt_cost * 8 // (10**6)
        if e.err_code[0].reason == 65:
            raise MemoryError(
                "Scrypt key derivation requires at least {} MB of memory. "
                "Please free up some memory and try again.".format(required_memory)
            )
        else:
            raise e
    else:
        return derived_key


def derive_wrapping_key_from_key_material(key_material: bytes, salt: bytes) -> bytes:
    """
    Uses HKDF to derive a 32 byte wrapping key to encrypt key material with.
    """

    wrapping_key = HKDF(
        algorithm=__HKDF_HASH_ALGORITHM,
        length=__WRAPPING_KEY_LENGTH,
        salt=salt,
        info=__WRAPPING_KEY_INFO,
        backend=default_backend()
    ).derive(key_material)
    return wrapping_key


class SecretBoxAuthenticationError(Exception):
    pass


def secret_box_encrypt(key_material: bytes, salt: bytes, plaintext: bytes) -> bytes:
    wrapping_key = derive_wrapping_key_from_key_material(key_material, salt)
    secret_box = SecretBox(wrapping_key)
    ciphertext = secret_box.encrypt(plaintext)
    return ciphertext


def secret_box_decrypt(key_material: bytes, salt: bytes, ciphertext: bytes) -> bytes:
    wrapping_key = derive_wrapping_key_from_key_material(key_material, salt)
    secret_box = SecretBox(wrapping_key)
    try:
        plaintext = secret_box.decrypt(ciphertext)
    except CryptoError as e:
        raise SecretBoxAuthenticationError from e
    return plaintext
