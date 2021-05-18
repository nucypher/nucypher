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

import contextlib
import datetime
import json
import os
import stat
from functools import partial
from ipaddress import IPv4Address
from json import JSONDecodeError
from os.path import abspath
from pathlib import Path
from random import SystemRandom
from typing import Callable, ClassVar, Dict, List, Tuple, Union, Optional

from constant_sorrow.constants import KEYRING_LOCKED
from cryptography import x509
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.backends.openssl.ec import _EllipticCurvePrivateKey
from cryptography.hazmat.primitives import serialization, hashes
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.ec import EllipticCurve
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from cryptography.hazmat.primitives.serialization import Encoding, load_pem_private_key
from cryptography.x509 import Certificate
from cryptography.x509.oid import NameOID
from mnemonic.mnemonic import Mnemonic
from nacl.exceptions import CryptoError
from nacl.secret import SecretBox
from umbral.keys import UmbralPrivateKey, UmbralPublicKey, derive_key_from_password, Scrypt

from nucypher.config.constants import DEFAULT_CONFIG_ROOT
from nucypher.crypto.constants import BLAKE2B
from nucypher.crypto.keypairs import HostingKeypair
from nucypher.crypto.powers import (DecryptingPower, DerivedKeyBasedPower, KeyPairBasedPower, SigningPower)
from nucypher.network.server import TLSHostingPower
from nucypher.utilities.logging import Logger

SYSTEM_RAND = SystemRandom()

# HKDF
__WRAPPING_KEY_LENGTH = 32
__HKDF_HASH_ALGORITHM = BLAKE2B
_WRAPPING_INFO = b'NuCypher/wrap'
_VERIFYING_INFO = b'NuCypher/verify'
_DECRYPTING_INFO = b'NuCypher/encrypt'
_DELEGATING_INFO = b'NuCypher/delegate'
_TLS_INFO = b'NuCypher/tls'

# Mnemonic
_MINIMUM_PASSWORD_LENGTH = 8
_ENTROPY_BITS = 256
_MNEMONIC_LANGUAGE = "english"

# Keystore
FILE_ENCODING = 'utf-8'
__PRIVATE_FLAGS = os.O_WRONLY | os.O_CREAT | os.O_EXCL    # Write, Create, Non-Existing
__PRIVATE_MODE = stat.S_IRUSR | stat.S_IWUSR              # 0o600

# TLS
_TLS_CERTIFICATE_ENCODING = Encoding.PEM
_TLS_CURVE = ec.SECP256R1

PrivateKeyData = Union[
    Dict[str, bytes],
    bytes,
    _EllipticCurvePrivateKey
]


def derive_umbral_key(key_material: bytes,
                      info: Optional[bytes] = None,
                      salt: Optional[bytes] = None,
                      ) -> bytes:

    if not salt or info:
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


def derive_wrapping_key(password: str, salt: bytes) -> bytes:
    """
    Derives a symmetric encryption key from a pair of password and salt.

    It uses Scrypt by default.
    """
    kdf = Scrypt()
    derived_key = kdf(password.encode(FILE_ENCODING), salt)
    return derived_key


#
# Keystore
#


def unlock_required(func):
    """Method decorator"""
    def wrapped(keyring=None, *args, **kwargs):
        if not keyring.is_unlocked:
            raise Keystore.Locked(f"{keyring.id} is locked. Unlock with .unlock")
        return func(keyring, *args, **kwargs)
    return wrapped


def _assemble_keystore(key: bytes, salt: bytes) -> Dict[str, bytes]:
    encoded_key_data = {'key': key, 'salt': salt}
    return encoded_key_data


def _read_keystore(path: Path, deserializer: Callable) -> Union[PrivateKeyData, bytes, str]:
    """Parses a keyfile and return decoded, deserialized key data."""
    with open(path, 'rb') as keyfile:
        key_data = keyfile.read()
        if deserializer:
            key_data = deserializer(key_data)
    return key_data


def _write_keystore(path: Path,
                    key_data: PrivateKeyData,
                    serializer: Union[Callable[[PrivateKeyData], bytes], None],
                    ) -> Path:
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
        key_data = serializer(key_data)
    with os.fdopen(keyfile_descriptor, 'wb') as keyfile:
        keyfile.write(key_data)
    return path


def _serialize_keystore(payload: PrivateKeyData) -> bytes:
    metadata = dict()
    for field, value in payload.items():
        metadata[field] = bytes(value).hex()
    try:
        metadata = json.dumps(metadata, indent=4)
    except JSONDecodeError:
        raise Keystore.Invalid("Invalid or corrupted key data")
    return bytes(metadata, encoding=FILE_ENCODING)


def _deserialize_keystore(payload: bytes) -> PrivateKeyData:
    key_metadata = payload.decode(encoding=FILE_ENCODING)
    try:
        key_metadata = json.loads(key_metadata)
    except JSONDecodeError:
        raise Keystore.Invalid("Invalid or corrupted key data")
    key_metadata = {field: bytes.fromhex(value)
                    for field, value in key_metadata.items()}
    return key_metadata


def validate_keystore_password(password: str) -> List:
    """
    Validate a password and return True or raise an error with a failure reason.
    NOTICE: Do not raise inside this function.
    """
    rules = (
        (bool(password), 'Password must not be blank.'),
        (len(password) >= _MINIMUM_PASSWORD_LENGTH,
         f'Password must be at least {_MINIMUM_PASSWORD_LENGTH} characters long.'),
    )
    failures = list()
    for rule, failure_message in rules:
        if not rule:
            failures.append(failure_message)
    return failures


def _generate_filepaths(parent: Path, account: str) -> dict:
    paths = {
        'keystore': parent / f'root-{account}.priv',  # TODO: Use timestamp prefix?
        'certificate': parent / f'{account}.pem'
    }
    return paths


class Keystore:

    log = Logger("keys")
    DEFAULT_PATH: Path = DEFAULT_CONFIG_ROOT / 'keystore'

    class Exists(FileExistsError):
        pass

    class Invalid(Exception):
        pass

    class Locked(RuntimeError):
        pass

    class AuthenticationFailed(RuntimeError):
        pass

    def __init__(self, keystore_dir: Path = DEFAULT_PATH, keystore_path: str = None):
        self.keystore_dir = keystore_dir
        self.keystore_path = keystore_path
        self.__secret = KEYRING_LOCKED

    def __del__(self) -> None:
        self.lock()

    def __decrypt_keystore(self, path: Path, password: str) -> bool:
        payload = _read_keystore(path, deserializer=_deserialize_keystore)
        wrapping_key = derive_wrapping_key(salt=payload['salt'], password=password)
        self.__secret = SecretBox(wrapping_key).decrypt(payload['key'])
        return True

    #
    # Public API
    #

    @property
    def signing_public_key(self):
        stamp_material = derive_umbral_key(key_material=self.__secret, info=_VERIFYING_INFO)
        key = UmbralPublicKey.from_bytes(stamp_material)
        return key

    @property
    def encrypting_public_key(self):
        stamp_material = derive_umbral_key(key_material=self.__secret, info=_DECRYPTING_INFO)
        key = UmbralPublicKey.from_bytes(stamp_material)
        return key

    @property
    def id(self) -> str:
        return self.signing_public_key.to_bytes().hex()

    @property
    def is_unlocked(self) -> bool:
        return self.__secret is not KEYRING_LOCKED

    def lock(self) -> bool:
        """Make efforts to remove references to the cached key data"""
        self.__secret = KEYRING_LOCKED
        return self.is_unlocked

    def unlock(self, password: str) -> bool:
        if self.is_unlocked:
            return self.is_unlocked
        try:
            self.__secret = self.__decrypt_keystore(path=self.keystore_path, password=password)
        except CryptoError:
            self.__secret = KEYRING_LOCKED
            raise self.AuthenticationFailed
        return self.is_unlocked

    @unlock_required
    def derive_crypto_power(self,
                            power_class: ClassVar,
                            host: Optional[str] = None
                            ) -> Union[KeyPairBasedPower, DerivedKeyBasedPower]:
        """
        Takes either a SigningPower or a DecryptingPower and returns
        either a SigningPower or DecryptingPower with the coinciding
        private key.
        """
        # Keypair-Based
        if issubclass(power_class, KeyPairBasedPower):

            codex = {SigningPower: _VERIFYING_INFO,
                     DecryptingPower: _DECRYPTING_INFO,
                     TLSHostingPower: _TLS_INFO}

            try:
                path = codex[power_class]
            except KeyError:
                failure_message = f"{power_class.__name__} is an invalid type for deriving a CryptoPower"
                raise TypeError(failure_message)

            if power_class is TLSHostingPower:  # TODO: something more elegant
                if not host:
                    raise ValueError('Host is required to derive a TLSHostingPower')
                tls_key_deserializer = partial(_deserialize_private_key_from_pem, password=self.__derived_key_material)
                private_key = _read_keystore(path=path, deserializer=tls_key_deserializer)
                keypair = HostingKeypair(host=host,
                                         private_key=private_key,
                                         checksum_address=self.checksum_address,  # TODO: remove or expand
                                         generate_certificate=False,
                                         certificate_filepath=self.__tls_certificate_path)
                new_cryptopower = TLSHostingPower(keypair=keypair, host=host)

            else:
                privkey = self.__decrypt_keystore(key_path=path)
                keypair = power_class._keypair_class(privkey)
                new_cryptopower = power_class(keypair=keypair)

        # Derived
        elif issubclass(power_class, DerivedKeyBasedPower):
            key_data = _read_keystore(self.__delegating_keypath, deserializer=_deserialize_keystore)
            wrap_key = hkdf(salt=key_data['wrap_salt'], key_material=self.__derived_key_material)
            keying_material = SecretBox(wrap_key).decrypt(key_data['key'])
            new_cryptopower = power_class(keying_material=keying_material)

        else:
            failure_message = "{} is an invalid type for deriving a CryptoPower.".format(power_class.__name__)
            raise ValueError(failure_message)

        return new_cryptopower

    @classmethod
    def generate(cls,
                 password: str,
                 rest: bool = False,
                 host: str = None,
                 keyring_root: str = None,
                 ) -> 'Keystore':

        keyring_root = keyring_root or cls.DEFAULT_PATH
        failures = validate_keystore_password(password)
        if failures:
            # TODO: Ensure this scope is separable from the scope containing the password
            raise cls.AuthenticationFailed(", ".join(failures))

        # Generate seed
        mnemonic = Mnemonic(_MNEMONIC_LANGUAGE)
        words = mnemonic.generate(strength=_ENTROPY_BITS)
        secret = mnemonic.to_entropy(words)

        # Generate wrapping key
        wrapping_key = derive_wrapping_key(salt=SYSTEM_RAND.randbytes(32), password=password)

        # delegating_keying_material = UmbralKeyingMaterial().to_bytes()
        entropy_ciphertext = bytes(SecretBox(symmetric_key).encrypt(secret))
        keystore_payload = _assemble_keystore(key_data=entropy_ciphertext,
                                              master_salt=symmetric_salt,
                                              wrap_salt=_WRAPPING_INFO)
        # Write Keystore
        keystore_path = cls._generate_base_filepaths(keyring_root=keyring_root)

        # Create base paths if the do not exist.
        os.makedirs(abspath(keyring_root), exist_ok=True, mode=0o700)
        keystore_path = _write_keystore(keypath=__key_filepaths['root'],
                                        key_data=encrypting_key_metadata,
                                        serializer=_serialize_keystore)

        # Commit
        keyring_args.update(
            keyring_root=keyring_root,
            root_key_path=keystore_path,
        )

        if rest is True:
            if not all((host, checksum_address)):  # TODO: Do we want to allow showing up with an old wallet and generating a new cert?  Probably.
                raise ValueError("host, checksum_address and curve are required to make a new keyring TLS certificate. Got {}, {}".format(host, curve))
            private_key, cert = _generate_tls_keys(host=host, checksum_address=checksum_address, curve=_TLS_CURVE)

            tls_key_serializer = partial(_serialize_private_key_to_pem, password=derived_key_material)
            tls_key_path = _write_keystore(keypath=__key_filepaths['tls'],
                                           key_data=private_key,
                                           serializer=tls_key_serializer)
            certificate_filepath = _write_tls_certificate(full_filepath=__key_filepaths['tls_certificate'],
                                                          certificate=cert)
            keyring_args.update(tls_certificate_path=certificate_filepath, tls_key_path=tls_key_path)

            keyring_instance = cls(account=checksum_address, **keyring_args)
            return keyring_instance

#
# TLS
#


def _write_tls_certificate(certificate: Certificate,
                           full_filepath: str,
                           force: bool = False,
                           ) -> str:
    cert_already_exists = os.path.isfile(full_filepath)
    if force is False and cert_already_exists:
        raise FileExistsError('A TLS certificate already exists at {}.'.format(full_filepath))

    with open(full_filepath, 'wb') as certificate_file:
        public_pem_bytes = certificate.public_bytes(__TLS_CERTIFICATE_ENCODING)
        certificate_file.write(public_pem_bytes)
    return full_filepath


def _read_tls_certificate(filepath: str) -> Certificate:
    """Deserialize an X509 certificate from a filepath"""
    try:
        with open(filepath, 'rb') as certificate_file:
            cert = x509.load_pem_x509_certificate(certificate_file.read(), backend=default_backend())
            return cert
    except FileNotFoundError:
        raise FileNotFoundError("No SSL certificate found at {}".format(filepath))


def _generate_tls_keys(host: str, checksum_address: str, curve: EllipticCurve) -> Tuple[_EllipticCurvePrivateKey, Certificate]:
    cert, private_key = generate_teacher_certificate(host=host, curve=curve, checksum_address=checksum_address)
    return private_key, cert


def _serialize_private_key_to_pem(key_data: PrivateKeyData, password: bytes) -> bytes:
    # TODO: Can we skip this check - below function will fail anyway, this is more informative though
    if not isinstance(key_data, _EllipticCurvePrivateKey):
        raise TypeError("Only _EllipticCurvePrivateKey is a valid type for serialization. Got {}".format(type(key_data)))
    return key_data.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.TraditionalOpenSSL,
        encryption_algorithm=serialization.BestAvailableEncryption(password=password)
    )


def _deserialize_private_key_from_pem(key_data: bytes, password: bytes) -> PrivateKeyData:
    private_key = load_pem_private_key(data=key_data, password=password)
    return private_key


def __generate_self_signed_certificate(host: str,
                                       curve: EllipticCurve = _TLS_CURVE,
                                       private_key: _EllipticCurvePrivateKey = None,
                                       days_valid: int = 365,  # TODO: Until end of stake / when to renew?
                                       checksum_address: str = None
                                       ) -> Tuple[Certificate, _EllipticCurvePrivateKey]:

    if not private_key:
        private_key = ec.generate_private_key(curve, default_backend())
    public_key = private_key.public_key()

    now = datetime.datetime.utcnow()
    fields = [
        x509.NameAttribute(NameOID.COMMON_NAME, host),
    ]
    if checksum_address:
        # Teacher Certificate
        pseudonym = x509.NameAttribute(NameOID.PSEUDONYM, checksum_address)
        fields.append(pseudonym)

    subject = issuer = x509.Name(fields)
    cert = x509.CertificateBuilder().subject_name(subject)
    cert = cert.issuer_name(issuer)
    cert = cert.public_key(public_key)
    cert = cert.serial_number(x509.random_serial_number())
    cert = cert.not_valid_before(now)
    cert = cert.not_valid_after(now + datetime.timedelta(days=days_valid))
    cert = cert.add_extension(x509.SubjectAlternativeName([x509.IPAddress(IPv4Address(host))]), critical=False)
    cert = cert.sign(private_key, hashes.SHA512(), default_backend())

    return cert, private_key


def generate_teacher_certificate(checksum_address: str, *args, **kwargs):
    cert = __generate_self_signed_certificate(checksum_address=checksum_address, *args, **kwargs)
    return cert


def generate_self_signed_certificate(*args, **kwargs):
    if 'checksum_address' in kwargs:
        raise ValueError("checksum address cannot be used to generate standard self-signed certificates.")
    cert = __generate_self_signed_certificate(checksum_address=None, *args, **kwargs)
    return cert
