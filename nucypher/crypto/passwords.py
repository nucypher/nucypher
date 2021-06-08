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

from typing import Optional

from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives.kdf.scrypt import Scrypt as CryptographyScrypt
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from nacl.secret import SecretBox
from nacl.utils import random as nacl_random
from nacl.exceptions import CryptoError

from nucypher.crypto.constants import BLAKE2B


# Keyring
__WRAPPING_KEY_LENGTH = 32 # TODO: should be the same as XCHACHA_KEY_SIZE
__WRAPPING_KEY_INFO = b'NuCypher-KeyWrap'
__HKDF_HASH_ALGORITHM = BLAKE2B


def derive_wrapping_key_from_key_material(salt: bytes,
                                          key_material: bytes,
                                          ) -> bytes:
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


class Scrypt:
    __DEFAULT_SCRYPT_COST = 20

    def __call__(self,
                 password: bytes,
                 salt: bytes,
                 **kwargs) -> bytes:
        """
        Derives a symmetric encryption key from a pair of password and salt.
        It also accepts an additional _scrypt_cost argument.
        WARNING: RFC7914 recommends that you use a 2^20 cost value for sensitive
        files. It is NOT recommended to change the `_scrypt_cost` value unless
        you know what you are doing.
        :param password: byte-encoded password used to derive a symmetric key
        :param salt: cryptographic salt added during key derivation
        :return:
        """

        _scrypt_cost = kwargs.get('_scrypt_cost', Scrypt.__DEFAULT_SCRYPT_COST)
        try:
            derived_key = CryptographyScrypt(
                salt=salt,
                length=SecretBox.KEY_SIZE,
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


def derive_key_from_password(password: bytes,
                             salt: bytes,
                             **kwargs) -> bytes:
    """
    Derives a symmetric encryption key from a pair of password and salt.
    It uses Scrypt by default.
    """
    kdf = kwargs.get('kdf', Scrypt)()
    derived_key = kdf(password, salt, **kwargs)
    return derived_key


class SecretBoxAuthenticationError(Exception):
    pass


def secret_box_encrypt(salt: bytes, key_material: bytes, plaintext: bytes) -> bytes:
    wrapping_key = derive_wrapping_key_from_key_material(salt, key_material)
    secret_box = SecretBox(wrapping_key)
    ciphertext = secret_box.encrypt(plaintext)
    return ciphertext


def secret_box_decrypt(salt: bytes, key_material: bytes, ciphertext: bytes) -> bytes:
    wrapping_key = derive_wrapping_key_from_key_material(salt, key_material)
    secret_box = SecretBox(wrapping_key)
    try:
        plaintext = secret_box.decrypt(ciphertext)
    except CryptoError as e:
        raise SecretBoxAuthenticationError from e
    return plaintext
