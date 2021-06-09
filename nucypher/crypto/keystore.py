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


import json
import os
import stat
import string
from json import JSONDecodeError
from os.path import abspath
from pathlib import Path
from secrets import token_bytes
from typing import Callable, ClassVar, Dict, List, Union, Optional, Tuple

import time
from constant_sorrow.constants import KEYSTORE_LOCKED
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from cryptography.hazmat.primitives.kdf.scrypt import Scrypt
from mnemonic.mnemonic import Mnemonic
from nacl.exceptions import CryptoError
from nacl.secret import SecretBox

from nucypher.config.constants import DEFAULT_CONFIG_ROOT
from nucypher.crypto.constants import BLAKE2B
from nucypher.crypto.keypairs import HostingKeypair
from nucypher.crypto.powers import (
    DecryptingPower,
    DerivedKeyBasedPower,
    KeyPairBasedPower,
    SigningPower,
    CryptoPowerUp,
    DelegatingPower
)
from nucypher.crypto.tls import generate_self_signed_certificate
from nucypher.network.server import TLSHostingPower
from umbral.keys import UmbralPrivateKey

# HKDF
__HKDF_HASH_ALGORITHM = BLAKE2B
__INFO_BASE = b'NuCypher/'
_WRAPPING_INFO = __INFO_BASE + b'wrap'
_VERIFYING_INFO = __INFO_BASE + b'verify'
_DECRYPTING_INFO = __INFO_BASE + b'encrypt'
_DELEGATING_INFO = __INFO_BASE + b'delegate'
_TLS_INFO = __INFO_BASE + b'tls'

# Wrapping key
_SALT_SIZE = 32
__WRAPPING_KEY_LENGTH = 32

# Mnemonic
_ENTROPY_BITS = 256
_MNEMONIC_LANGUAGE = "english"

# Keystore File
FILE_ENCODING = 'utf-8'
__PRIVATE_FLAGS = os.O_WRONLY | os.O_CREAT | os.O_EXCL  # Write, Create, Non-Existing
__PRIVATE_MODE = stat.S_IRUSR | stat.S_IWUSR            # 0o600


class InvalidPassword(ValueError):
    pass


def __hkdf(key_material: bytes,
           info: Optional[bytes] = None,
           salt: Optional[bytes] = None,
           ) -> bytes:

    if not salt and not info:
        raise ValueError('Info or salt must be provided.')
    info = info or bytes()
    salt = salt or bytes()

    kdf = HKDF(
        algorithm=__HKDF_HASH_ALGORITHM,
        length=__WRAPPING_KEY_LENGTH,
        salt=salt,
        info=info,
        backend=default_backend()
    )
    return kdf.derive(key_material)


def _derive_wrapping_key(password: str, salt: bytes) -> bytes:
    """Derives a symmetric encryption key from password and salt."""
    kdf = Scrypt(
        salt=salt,
        length=__WRAPPING_KEY_LENGTH,
        n=2 ** 14,
        r=8,
        p=1,
        backend=default_backend()
    )
    derived_key = kdf.derive(key_material=password.encode())
    return derived_key


def _derive_umbral_key(material: bytes, info: bytes) -> UmbralPrivateKey:
    material = __hkdf(key_material=material, info=info)
    __private = UmbralPrivateKey.from_bytes(key_bytes=material)
    return __private


def _assemble_keystore(encrypted_secret: bytes, salt: bytes) -> Dict[str, Union[str, bytes]]:
    encoded_key_data = {
        'version': '2.0',
        'created': str(time.time()),
        'key': encrypted_secret,
        'salt': salt
    }
    return encoded_key_data


def _read_keystore(path: Path, deserializer: Callable) -> Dict[str, Union[str, bytes]]:
    """Parses a keyfile and return decoded, deserialized key data."""
    with open(path, 'rb') as keyfile:
        key_data = keyfile.read()
        if deserializer:
            key_data = deserializer(key_data)
    return key_data


def _write_keystore(path: Path, payload: Dict[str, bytes], serializer: Callable) -> Path:
    """
    Creates a permissioned keyfile and save it to the local filesystem.
    The file must be created in this call, and will fail if the path exists.
    Returns the filepath string used to write the keyfile.

    Note: getting and setting the umask is not thread-safe!

    See linux open docs: http://man7.org/linux/man-pages/man2/open.2.html
    ---------------------------------------------------------------------
    O_CREAT - If pathname does not exist, create it as a regular file.


    O_EXCL - Ensure that this call creates the file: if this flag is
             specified in conjunction with O_CREAT, and pathname already
             exists, then open() fails with the error EEXIST.
    ---------------------------------------------------------------------
    """

    if path.exists():
        raise Keystore.Exists(f"Private keyfile {path} already exists.")
    try:
        keyfile_descriptor = os.open(path, flags=__PRIVATE_FLAGS, mode=__PRIVATE_MODE)
    finally:
        os.umask(0)  # Set the umask to 0 after opening
    if serializer:
        payload = serializer(payload)
    with os.fdopen(keyfile_descriptor, 'wb') as keyfile:
        keyfile.write(payload)
    return path


def _serialize_keystore(payload: Dict) -> bytes:
    for field in ('key', 'salt'):
        payload[field] = bytes(payload[field]).hex()
    try:
        metadata = json.dumps(payload, indent=4)
    except JSONDecodeError:
        raise Keystore.Invalid("Invalid or corrupted key data")
    return bytes(metadata, encoding=FILE_ENCODING)


def _deserialize_keystore(payload: bytes):
    payload = payload.decode(encoding=FILE_ENCODING)
    try:
        payload = json.loads(payload)
    except JSONDecodeError:
        raise Keystore.Invalid("Invalid or corrupted key data")
    for field in ('key', 'salt'):
        payload[field] = bytes.fromhex(payload[field])
    return payload


def generate_keystore_filepath(parent: Path, id: str) -> Path:
    utc_nowish = int(time.time())  # epoch
    path = Path(parent) / f'{utc_nowish}-{id}.priv'
    return path


def validate_keystore_password(password: str) -> List:
    """
    NOTICE: Do not raise inside this function.
    """
    rules = (
        (bool(password), 'Password must not be blank.'),
        (len(password) >= Keystore._MINIMUM_PASSWORD_LENGTH,
         f'Password must be at least {Keystore._MINIMUM_PASSWORD_LENGTH} characters long.'),
    )
    failures = list()
    for rule, failure_message in rules:
        if not rule:
            failures.append(failure_message)
    return failures


def validate_keystore_filename(path: Path) -> None:
    base_name = path.name.rstrip('.' + Keystore._SUFFIX)
    parts = base_name.split(Keystore._DELIMITER)

    try:
        created, keystore_id = parts
    except ValueError:
        raise Keystore.Invalid(f'{path} is not a valid keystore filename')

    validators = (
        bool(len(keystore_id) == Keystore._ID_SIZE),
        all(char in string.hexdigits for char in keystore_id)
    )

    valid_path = all(validators)
    if not valid_path:
        raise Keystore.Invalid(f'{path} is not a valid keystore filename')


def _parse_path(path: Path) -> Tuple[int, str]:

    # validate keystore file
    path = Path(path)
    if not path.exists():
        raise Keystore.NotFound(f"Keystore '{path}' does not exist.")
    if not path.is_file():
        raise ValueError('Keystore path must be a file.')
    if not path.match(f'*{Keystore._DELIMITER}*.{Keystore._SUFFIX}'):
        Keystore.Invalid(f'{path} is not a valid keystore filename')

    # dissect keystore filename
    validate_keystore_filename(path)
    base_name = path.name.rstrip('.'+Keystore._SUFFIX)
    parts = base_name.split(Keystore._DELIMITER)
    created, keystore_id = parts
    return created, keystore_id


def _derive_hosting_power(host: str, private_key: UmbralPrivateKey) -> TLSHostingPower:
    certificate, _private_key = generate_self_signed_certificate(host=host, private_key=private_key)
    keypair = HostingKeypair(host=host, certificate=certificate, generate_certificate=False)
    power = TLSHostingPower(keypair=keypair, host=host)
    return power


class Keystore:

    # Wrapping Key
    _MINIMUM_PASSWORD_LENGTH = 8
    _ID_SIZE = 32

    # Filepath
    _DEFAULT_DIR: Path = DEFAULT_CONFIG_ROOT / 'keystore'
    _DELIMITER = '-'
    _SUFFIX = 'priv'

    # Powers derivation
    __HKDF_INFO = {SigningPower: _VERIFYING_INFO,
                   DecryptingPower: _DECRYPTING_INFO,
                   DelegatingPower: _DELEGATING_INFO,
                   TLSHostingPower: _TLS_INFO}

    class Exists(FileExistsError):
        pass

    class Invalid(Exception):
        pass

    class NotFound(FileNotFoundError):
        pass

    class Locked(RuntimeError):
        pass

    class AuthenticationFailed(RuntimeError):
        pass

    def __init__(self, keystore_path: Path):
        self.keystore_path = keystore_path
        self.__created, self.__id = _parse_path(keystore_path)
        self.__secret = KEYSTORE_LOCKED

    def __decrypt_keystore(self, path: Path, password: str) -> bool:
        payload = _read_keystore(path, deserializer=_deserialize_keystore)
        wrapping_key = _derive_wrapping_key(salt=payload['salt'], password=password)
        self.__secret = SecretBox(wrapping_key).decrypt(payload['key'])
        return True

    @staticmethod
    def __save(secret: bytes, password: str, keystore_dir: Optional[Path] = None) -> Path:
        failures = validate_keystore_password(password)
        if failures:
            # TODO: Ensure this scope is separable from the scope containing the password
            #       to help avoid unintentional logging of the password.
            raise InvalidPassword(''.join(failures))

        # Derive verifying key (used as ID)
        verifying_key = _derive_umbral_key(material=secret, info=_VERIFYING_INFO)
        keystore_id = verifying_key.to_bytes().hex()[:Keystore._ID_SIZE]

        # Generate paths
        keystore_dir = keystore_dir or Keystore._DEFAULT_DIR
        os.makedirs(abspath(keystore_dir), exist_ok=True, mode=0o700)
        keystore_path = generate_keystore_filepath(parent=keystore_dir, id=keystore_id)

        # Encrypt secret
        __salt = token_bytes(_SALT_SIZE)
        __wrapping_key = _derive_wrapping_key(salt=__salt, password=password)
        encrypted_secret = bytes(SecretBox(__wrapping_key).encrypt(secret))

        # Create keystore file
        keystore_payload = _assemble_keystore(encrypted_secret=encrypted_secret, salt=__salt)
        _write_keystore(path=keystore_path, payload=keystore_payload, serializer=_serialize_keystore)

        return keystore_path

    #
    # Public API
    #

    @classmethod
    def load(cls, id: str, keystore_dir: Path = _DEFAULT_DIR) -> 'Keystore':
        filepath = generate_keystore_filepath(parent=keystore_dir, id=id)
        instance = cls(keystore_path=filepath)
        return instance

    @classmethod
    def restore(cls, words: str, password: str, keystore_dir: Optional[Path] = None) -> 'Keystore':
        __mnemonic = Mnemonic(_MNEMONIC_LANGUAGE)
        __secret = __mnemonic.to_entropy(words)
        path = Keystore.__save(secret=__secret, password=password, keystore_dir=keystore_dir)
        keystore = cls(keystore_path=path)
        return keystore

    @classmethod
    def generate(cls, password: str, keystore_dir: Optional[Path] = None) -> 'Keystore':
        mnemonic = Mnemonic(_MNEMONIC_LANGUAGE)
        __words = mnemonic.generate(strength=_ENTROPY_BITS)
        __secret = mnemonic.to_entropy(__words)
        path = Keystore.__save(secret=__secret, password=password, keystore_dir=keystore_dir)
        keystore = cls(keystore_path=path)
        return keystore

    @property
    def id(self) -> str:
        return self.__id

    @property
    def is_unlocked(self) -> bool:
        return self.__secret is not KEYSTORE_LOCKED

    def lock(self) -> bool:
        self.__secret = KEYSTORE_LOCKED
        return self.is_unlocked

    def unlock(self, password: str) -> bool:
        try:
            self.__decrypt_keystore(path=self.keystore_path, password=password)
        except CryptoError:
            self.__secret = KEYSTORE_LOCKED
            raise self.AuthenticationFailed
        return self.is_unlocked

    def derive_crypto_power(self,
                            power_class: ClassVar[CryptoPowerUp],
                            *power_args, **power_kwargs
                            ) -> Union[KeyPairBasedPower, DerivedKeyBasedPower]:

        if not self.is_unlocked:
            raise Keystore.Locked(f"{self.id} is locked. Unlock with .unlock")
        try:
            info = self.__HKDF_INFO[power_class]
        except KeyError:
            failure_message = f"{power_class.__name__} is an invalid type for deriving a CryptoPower"
            raise TypeError(failure_message)
        else:
            __private_key = _derive_umbral_key(material=self.__secret, info=info)

        if power_class is TLSHostingPower:  # TODO: something more elegant?
            power = _derive_hosting_power(private_key=__private_key, *power_args, **power_kwargs)

        elif issubclass(power_class, KeyPairBasedPower):
            keypair = power_class._keypair_class(__private_key)
            power = power_class(keypair=keypair, *power_args, **power_kwargs)

        elif issubclass(power_class, DerivedKeyBasedPower):
            power = power_class(keying_material=__private_key.to_bytes(), *power_args, **power_kwargs)

        else:
            failure_message = f"{power_class.__name__} is an invalid type for deriving a CryptoPower."
            raise ValueError(failure_message)

        return power
