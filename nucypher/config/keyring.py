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
import base64
import contextlib
import json
import os
import shutil
import stat
from json import JSONDecodeError

from cryptography import x509
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.backends.openssl.ec import _EllipticCurvePrivateKey
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.ec import EllipticCurve
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from cryptography.hazmat.primitives.serialization import Encoding
from cryptography.x509 import Certificate
from eth_account import Account
from eth_keys import KeyAPI as EthKeyAPI
from eth_utils import to_checksum_address, is_checksum_address
from nacl.exceptions import CryptoError
from nacl.secret import SecretBox
from twisted.logger import Logger
from typing import ClassVar, Tuple, Callable, Union, Dict, List
from umbral.keys import UmbralPrivateKey, UmbralPublicKey, UmbralKeyingMaterial, derive_key_from_password

from constant_sorrow.constants import KEYRING_LOCKED
from nucypher.config.constants import DEFAULT_CONFIG_ROOT
from nucypher.crypto.api import generate_self_signed_certificate
from nucypher.crypto.constants import BLAKE2B
from nucypher.crypto.powers import SigningPower, DecryptingPower, KeyPairBasedPower, DerivedKeyBasedPower
from nucypher.network.server import TLSHostingPower

FILE_ENCODING = 'utf-8'

KEY_ENCODER = base64.urlsafe_b64encode
KEY_DECODER = base64.urlsafe_b64decode

TLS_CERTIFICATE_ENCODING = Encoding.PEM

__PRIVATE_FLAGS = os.O_WRONLY | os.O_CREAT | os.O_EXCL    # Write, Create, Non-Existing
__PRIVATE_MODE = stat.S_IRUSR | stat.S_IWUSR              # 0o600

__PUBLIC_FLAGS = os.O_WRONLY | os.O_CREAT | os.O_EXCL     # Write, Create, Non-Existing
__PUBLIC_MODE = stat.S_IRUSR | stat.S_IWUSR | stat.S_IRGRP | stat.S_IROTH  # 0o644

# Keyring
__WRAPPING_KEY_LENGTH = 32
__WRAPPING_KEY_INFO = b'NuCypher-KeyWrap'
__HKDF_HASH_ALGORITHM = BLAKE2B


def unlock_required(func):
    """Method decorator"""

    def wrapped(keyring=None, *args, **kwargs):
        if not keyring.is_unlocked:
            raise NucypherKeyring.KeyringLocked("{} is locked. Unlock with .unlock".format(keyring.account))
        return func(keyring, *args, **kwargs)

    return wrapped


def _assemble_key_data(key_data: bytes,
                       master_salt: bytes,
                       wrap_salt: bytes) -> Dict[str, bytes]:
    encoded_key_data = {
        'key': key_data,
        'master_salt': master_salt,
        'wrap_salt': wrap_salt,
    }
    return encoded_key_data


def _read_keyfile(keypath: str,
                  deserializer: Union[Callable, None]
                  ) -> Union[Dict[str, bytes], bytes, str]:
    """
    Parses a keyfile and return decoded, deserialized key metadata.
    """
    with open(keypath, 'rb') as keyfile:
        key_metadata = keyfile.read()
        if deserializer:
            key_metadata = deserializer(key_metadata)
    return key_metadata


def _write_private_keyfile(keypath: str,
                           key_data: Dict[str, bytes],
                           serializer: Union[Callable, None]
                           ) -> str:
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

    try:
        keyfile_descriptor = os.open(keypath, flags=__PRIVATE_FLAGS, mode=__PRIVATE_MODE)
    finally:
        os.umask(0)  # Set the umask to 0 after opening
    if serializer:
        key_data = serializer(key_data)
    with os.fdopen(keyfile_descriptor, 'wb') as keyfile:
        keyfile.write(key_data)
    return keypath


def _write_public_keyfile(keypath: str,
                          key_data: bytes) -> str:
    """
    Creates a permissioned keyfile and save it to the local filesystem.
    The file must be created in this call, and will fail if the path exists.
    Returns the filepath string used to write the keyfile.

    Note: getting and setting the umask is not thread-safe!

    See Linux open docs: http://man7.org/linux/man-pages/man2/open.2.html
    ---------------------------------------------------------------------
    O_CREAT - If pathname does not exist, create it as a regular file.


    O_EXCL - Ensure that this call creates the file: if this flag is
             specified in conjunction with O_CREAT, and pathname already
             exists, then open() fails with the error EEXIST.
    ---------------------------------------------------------------------
    """

    try:
        keyfile_descriptor = os.open(keypath, flags=__PUBLIC_FLAGS, mode=__PUBLIC_MODE)
    finally:
        os.umask(0)  # Set the umask to 0 after opening
    with os.fdopen(keyfile_descriptor, 'wb') as keyfile:
        keyfile.write(key_data)
    return keypath


def _write_tls_certificate(certificate: Certificate,
                           full_filepath: str,
                           force: bool = False,
                           ) -> str:
    cert_already_exists = os.path.isfile(full_filepath)
    if force is False and cert_already_exists:
        raise FileExistsError('A TLS certificate already exists at {}.'.format(full_filepath))

    with open(full_filepath, 'wb') as certificate_file:
        public_pem_bytes = certificate.public_bytes(TLS_CERTIFICATE_ENCODING)
        certificate_file.write(public_pem_bytes)
    return full_filepath


def _read_tls_public_certificate(filepath: str) -> Certificate:
    """Deserialize an X509 certificate from a filepath"""
    try:
        with open(filepath, 'rb') as certificate_file:
            cert = x509.load_pem_x509_certificate(certificate_file.read(), backend=default_backend())
            return cert
    except FileNotFoundError:
        raise FileNotFoundError("No SSL certificate found at {}".format(filepath))


#
# Key wrapping
#
def _derive_wrapping_key_from_key_material(salt: bytes,
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


#
# Keypair Generation
#


def _generate_encryption_keys() -> Tuple[UmbralPrivateKey, UmbralPublicKey]:
    """Use pyUmbral keys to generate a new encrypting key pair"""
    privkey = UmbralPrivateKey.gen_key()
    pubkey = privkey.get_pubkey()
    return privkey, pubkey


def _generate_signing_keys() -> Tuple[UmbralPrivateKey, UmbralPublicKey]:
    """
    TODO: Do we really want to use Umbral keys for signing? Perhaps we can use Curve25519/EdDSA for signatures?
    """
    privkey = UmbralPrivateKey.gen_key()
    pubkey = privkey.get_pubkey()
    return privkey, pubkey


def _generate_wallet(password: str) -> Tuple[str, dict]:
    """Create a new wallet address and private "transacting" key encrypted with the password"""
    account = Account.create(extra_entropy=os.urandom(32))  # max out entropy for keccak256
    encrypted_wallet_data = Account.encrypt(private_key=account.privateKey, password=password)
    return account.address, encrypted_wallet_data


def _generate_tls_keys(host: str, checksum_address: str, curve: EllipticCurve) -> Tuple[_EllipticCurvePrivateKey, Certificate]:
    cert, private_key = generate_self_signed_certificate(host=host, curve=curve, checksum_address=checksum_address)
    return private_key, cert


class _PrivateKeySerializer:

    def __serialize(self,
                    key_metadata: Dict[str, bytes],
                    encoding: str,
                    nested_serializer: Callable = KEY_ENCODER,
                    ) -> bytes:

        if nested_serializer:
            metadata = dict()
            for field, value in key_metadata.items():
                metadata[field] = nested_serializer(bytes(value)).decode()
        try:
            metadata = json.dumps(metadata, indent=4)
        except JSONDecodeError:
            raise NucypherKeyring.KeyringError("Invalid or corrupted key data")
        except TypeError:
            raise
        return bytes(metadata, encoding=encoding)

    def __deserialize(self,
                      key_metadata: bytes,
                      encoding: str,
                      nested_deserializer: Callable = KEY_DECODER
                      ) -> Dict[str, bytes]:

        key_metadata = key_metadata.decode(encoding=encoding)
        try:
            key_metadata = json.loads(key_metadata)
        except JSONDecodeError:
            raise NucypherKeyring.KeyringError("Invalid or corrupted key data")
        if nested_deserializer:
            key_metadata = {field: nested_deserializer(value.encode())
                            for field, value in key_metadata.items()}
        return key_metadata

    def __call__(self, data: Union[bytes, dict]):
        if isinstance(data, bytes):
            return self.__deserialize(key_metadata=data,
                                      encoding=FILE_ENCODING,
                                      nested_deserializer=KEY_DECODER)
        elif isinstance(data, dict):
            return self.__serialize(key_metadata=data,
                                    encoding=FILE_ENCODING,
                                    nested_serializer=KEY_ENCODER)
        else:
            raise TypeError("Only bytes or dict are valid types for serialization. Got {}".format(type(data)))


class NucypherKeyring:
    """
    Handles keys for a single identity, recognized by account.
    Warning: This class handles private keys!

    - keyring
        - .private
            - key.priv
            - key.priv.pem
        - public
            - key.pub
            - cert.pem

    """

    __default_keyring_root = os.path.join(DEFAULT_CONFIG_ROOT, 'keyring')
    _private_key_serializer = _PrivateKeySerializer()
    __DEFAULT_TLS_CURVE = ec.SECP384R1

    log = Logger("keys")

    class KeyringError(Exception):
        pass

    class KeyringLocked(KeyringError):
        pass

    class AuthenticationFailed(KeyringError):
        pass

    def __init__(self,
                 account: str,
                 keyring_root: str = None,
                 root_key_path: str = None,
                 pub_root_key_path: str = None,
                 signing_key_path: str = None,
                 pub_signing_key_path: str = None,
                 delegating_key_path: str = None,
                 tls_key_path: str = None,
                 tls_certificate_path: str = None,
                 ) -> None:
        """
        Generates a NuCypherKeyring instance with the provided key paths falling back to default keyring paths.
        """

        # Identity
        self.__account = account
        self.__keyring_root = keyring_root or self.__default_keyring_root

        # Generate base filepaths
        __default_base_filepaths = self._generate_base_filepaths(keyring_root=self.__keyring_root)
        self.__public_key_dir = __default_base_filepaths['public_key_dir']
        self.__private_key_dir = __default_base_filepaths['private_key_dir']

        # Check for overrides
        __default_key_filepaths = self._generate_key_filepaths(account=self.__account,
                                                               public_key_dir=self.__public_key_dir,
                                                               private_key_dir=self.__private_key_dir)

        # Private
        self.__root_keypath = root_key_path or __default_key_filepaths['root']
        self.__signing_keypath = signing_key_path or __default_key_filepaths['signing']
        self.__delegating_keypath = delegating_key_path or __default_key_filepaths['delegating']
        self.__tls_keypath = tls_key_path or __default_key_filepaths['tls']

        # Public
        self.__root_pub_keypath = pub_root_key_path or __default_key_filepaths['root_pub']
        self.__signing_pub_keypath = pub_signing_key_path or __default_key_filepaths['signing_pub']
        self.__tls_certificate = tls_certificate_path or __default_key_filepaths['tls_certificate']

        # Set Initial State
        self.__derived_key_material = KEYRING_LOCKED

    def __del__(self) -> None:
        self.lock()

    #
    # Public Keys
    #
    @property
    def checksum_address(self) -> str:
        return to_checksum_address(self.__account)

    @property
    def federated_address(self) -> str:
        signature_pubkey = self.signing_public_key
        uncompressed_bytes = signature_pubkey.to_bytes(is_compressed=False)
        without_prefix = uncompressed_bytes[1:]
        verifying_key_as_eth_key = EthKeyAPI.PublicKey(without_prefix)
        address = verifying_key_as_eth_key.to_checksum_address()
        return to_checksum_address(address)

    @property
    def signing_public_key(self):
        signature_pubkey_bytes = _read_keyfile(keypath=self.__signing_pub_keypath, deserializer=None)
        signature_pubkey = UmbralPublicKey.from_bytes(signature_pubkey_bytes)
        return signature_pubkey

    @property
    def encrypting_public_key(self):
        encrypting_pubkey_bytes = _read_keyfile(keypath=self.__root_pub_keypath, deserializer=None)
        encrypting_pubkey = UmbralPublicKey.from_bytes(encrypting_pubkey_bytes)
        return encrypting_pubkey

    @property
    def certificate_filepath(self) -> str:
        return self.__tls_certificate

    #
    # Utils
    #
    @staticmethod
    def _generate_base_filepaths(keyring_root: str) -> Dict[str, str]:
        base_paths = dict(public_key_dir=os.path.join(keyring_root, 'public'),
                          private_key_dir=os.path.join(keyring_root, 'private'))
        return base_paths

    @staticmethod
    def _generate_key_filepaths(public_key_dir: str,
                                private_key_dir: str,
                                account: str) -> dict:
        __key_filepaths = {
            'root': os.path.join(private_key_dir, 'root-{}.priv'.format(account)),
            'root_pub': os.path.join(public_key_dir, 'root-{}.pub'.format(account)),
            'signing': os.path.join(private_key_dir, 'signing-{}.priv'.format(account)),
            'delegating': os.path.join(private_key_dir, 'delegating-{}.priv'.format(account)),
            'signing_pub': os.path.join(public_key_dir, 'signing-{}.pub'.format(account)),
            'tls': os.path.join(private_key_dir, '{}.priv.pem'.format(account)),
            'tls_certificate': os.path.join(public_key_dir, '{}.pem'.format(account))
        }

        return __key_filepaths

    @unlock_required
    def __decrypt_keyfile(self, key_path: str) -> UmbralPrivateKey:
        """Returns plaintext version of decrypting key."""
        key_data = _read_keyfile(key_path, deserializer=self._private_key_serializer)
        wrap_key = _derive_wrapping_key_from_key_material(salt=key_data['wrap_salt'],
                                                          key_material=self.__derived_key_material)
        plain_umbral_key = UmbralPrivateKey.from_bytes(key_bytes=key_data['key'], wrapping_key=wrap_key)
        return plain_umbral_key

    #
    # Public API
    #
    @property
    def account(self) -> str:
        return self.__account

    @property
    def is_unlocked(self) -> bool:
        return self.__derived_key_material is not KEYRING_LOCKED

    def lock(self) -> bool:
        """Make efforts to remove references to the cached key data"""
        self.__derived_key_material = KEYRING_LOCKED
        return self.is_unlocked

    def unlock(self, password: str) -> bool:
        if self.is_unlocked:
            return self.is_unlocked
        key_data = _read_keyfile(keypath=self.__root_keypath, deserializer=self._private_key_serializer)
        self.log.info("Unlocking keyring.")
        try:
            derived_key = derive_key_from_password(password=password.encode(), salt=key_data['master_salt'])
        except CryptoError:
            self.log.info("Keyring unlock failed.")
            raise self.AuthenticationFailed
        else:
            self.__derived_key_material = derived_key
            self.log.info("Finished unlocking.")
        return self.is_unlocked

    @unlock_required
    def derive_crypto_power(self, power_class: ClassVar) -> Union[KeyPairBasedPower, DerivedKeyBasedPower]:
        """
        Takes either a SigningPower or an DecryptingPower and returns
        either a SigningPower or DecryptingPower with the coinciding
        private key.

        TODO: Derive a key from the root_key.
        """
        # Keypair-Based
        if issubclass(power_class, KeyPairBasedPower):

            codex = {SigningPower: self.__signing_keypath,
                     DecryptingPower: self.__root_keypath,
                     TLSHostingPower: self.__tls_keypath}

            # Create Power
            try:
                umbral_privkey = self.__decrypt_keyfile(codex[power_class])
                keypair = power_class._keypair_class(umbral_privkey)
                new_cryptopower = power_class(keypair=keypair)
            except KeyError:
                failure_message = "{} is an invalid type for deriving a CryptoPower".format(power_class.__name__)
                raise TypeError(failure_message)

        # Derived
        elif issubclass(power_class, DerivedKeyBasedPower):
            key_data = _read_keyfile(self.__delegating_keypath, deserializer=self._private_key_serializer)
            wrap_key = _derive_wrapping_key_from_key_material(salt=key_data['wrap_salt'], key_material=self.__derived_key_material)
            keying_material = SecretBox(wrap_key).decrypt(key_data['key'])
            new_cryptopower = power_class(keying_material=keying_material)

        else:
            failure_message = "{} is an invalid type for deriving a CryptoPower.".format(power_class.__name__)
            raise ValueError(failure_message)

        return new_cryptopower

    #
    # Create
    #
    @classmethod
    def generate(cls,
                 password: str,
                 encrypting: bool,
                 rest: bool,
                 host: str = None,
                 curve: EllipticCurve = None,
                 keyring_root: str = None,
                 checksum_address: str = None
                 ) -> 'NucypherKeyring':
        """
        Generates new encrypting, signing, and wallet keys encrypted with the password,
        respectively saving keyfiles on the local filesystem from *default* paths,
        returning the corresponding Keyring instance.
        """

        failures = cls.validate_password(password)
        if failures:
            raise cls.AuthenticationFailed(", ".join(failures))  # TODO: Ensure this scope is seperable from the scope containing the password

        if not any((encrypting, rest)):
            raise ValueError('Either "encrypting", "wallet", or "tls" must be True '
                             'to generate new keys, or set "no_keys" to True to skip generation.')

        if curve is None:
            curve = cls.__DEFAULT_TLS_CURVE

        if checksum_address is not None and not is_checksum_address(checksum_address):
            raise ValueError(f"{checksum_address} is not a valid ethereum checksum address")

        _base_filepaths = cls._generate_base_filepaths(keyring_root=keyring_root)
        _public_key_dir = _base_filepaths['public_key_dir']
        _private_key_dir = _base_filepaths['private_key_dir']

        # Write to disk
        if not os.path.isdir(_public_key_dir):
            os.mkdir(_public_key_dir, mode=0o744)   # public dir

        if not os.path.isdir(_private_key_dir):
            os.mkdir(_private_key_dir, mode=0o700)  # private dir

        #
        # Generate New Keypairs
        #

        keyring_args = dict()

        if encrypting is True:
            signing_private_key, signing_public_key = _generate_signing_keys()

            if checksum_address is None:
                uncompressed_bytes = signing_public_key.to_bytes(is_compressed=False)
                without_prefix = uncompressed_bytes[1:]
                verifying_key_as_eth_key = EthKeyAPI.PublicKey(without_prefix)
                checksum_address = verifying_key_as_eth_key.to_checksum_address()

        __key_filepaths = cls._generate_key_filepaths(account=checksum_address,
                                                      private_key_dir=_private_key_dir,
                                                      public_key_dir=_public_key_dir)
        if encrypting is True:
            encrypting_private_key, encrypting_public_key = _generate_encryption_keys()
            delegating_keying_material = UmbralKeyingMaterial().to_bytes()

            # Derive Wrapping Keys
            password_salt, encrypting_salt, signing_salt, delegating_salt = (os.urandom(32) for _ in range(4))

            cls.log.info("About to derive key from password.")
            derived_key_material = derive_key_from_password(salt=password_salt, password=password.encode())
            encrypting_wrap_key = _derive_wrapping_key_from_key_material(salt=encrypting_salt, key_material=derived_key_material)
            signature_wrap_key = _derive_wrapping_key_from_key_material(salt=signing_salt, key_material=derived_key_material)
            delegating_wrap_key = _derive_wrapping_key_from_key_material(salt=delegating_salt, key_material=derived_key_material)

            # Encapsulate Private Keys
            encrypting_key_data = encrypting_private_key.to_bytes(wrapping_key=encrypting_wrap_key)
            signing_key_data = signing_private_key.to_bytes(wrapping_key=signature_wrap_key)
            delegating_key_data = bytes(SecretBox(delegating_wrap_key).encrypt(delegating_keying_material))

            # Assemble Private Keys
            encrypting_key_metadata = _assemble_key_data(key_data=encrypting_key_data,
                                                         master_salt=password_salt,
                                                         wrap_salt=encrypting_salt)
            signing_key_metadata = _assemble_key_data(key_data=signing_key_data,
                                                      master_salt=password_salt,
                                                      wrap_salt=signing_salt)
            delegating_key_metadata = _assemble_key_data(key_data=delegating_key_data,
                                                         master_salt=password_salt,
                                                         wrap_salt=delegating_salt)

            # Write Private Keys
            rootkey_path = _write_private_keyfile(keypath=__key_filepaths['root'],
                                                  key_data=encrypting_key_metadata,
                                                  serializer=cls._private_key_serializer)
            sigkey_path = _write_private_keyfile(keypath=__key_filepaths['signing'],
                                                 key_data=signing_key_metadata,
                                                 serializer=cls._private_key_serializer)
            delegating_key_path = _write_private_keyfile(keypath=__key_filepaths['delegating'],
                                                         key_data=delegating_key_metadata,
                                                         serializer=cls._private_key_serializer)

            # Write Public Keys
            root_keypath = _write_public_keyfile(__key_filepaths['root_pub'], encrypting_public_key.to_bytes())
            signing_keypath = _write_public_keyfile(__key_filepaths['signing_pub'], signing_public_key.to_bytes())

            # Commit
            keyring_args.update(
                keyring_root=keyring_root or cls.__default_keyring_root,
                root_key_path=rootkey_path,
                pub_root_key_path=root_keypath,
                signing_key_path=sigkey_path,
                pub_signing_key_path=signing_keypath,
                delegating_key_path=delegating_key_path,
            )

        if rest is True:
            if not all((host, curve, checksum_address)):  # TODO: Do we want to allow showing up with an old wallet and generating a new cert?  Probably.
                raise ValueError("host, checksum_address and curve are required to make a new keyring TLS certificate. Got {}, {}".format(host, curve))
            private_key, cert = _generate_tls_keys(host=host, checksum_address=checksum_address, curve=curve)

            def __serialize_pem(pk):
                return pk.private_bytes(
                    encoding=serialization.Encoding.PEM,
                    format=serialization.PrivateFormat.TraditionalOpenSSL,
                    encryption_algorithm=serialization.BestAvailableEncryption(password=derived_key_material)
                )

            tls_key_path = _write_private_keyfile(keypath=__key_filepaths['tls'], key_data=__serialize_pem(pk=private_key), serializer=None)
            certificate_filepath = _write_tls_certificate(full_filepath=__key_filepaths['tls_certificate'], certificate=cert)
            keyring_args.update(tls_certificate_path=certificate_filepath, tls_key_path=tls_key_path)

        keyring_instance = cls(account=checksum_address, **keyring_args)
        return keyring_instance

    @staticmethod
    def validate_password(password: str) -> List:
        """
        Validate a password and return True or raise an error with a failure reason.

        NOTICE: Do not raise inside this function.
        """
        rules = (
            (bool(password), 'Password must not be blank.'),
            (len(password) >= 16, 'Password is too short, must be >= 16 chars.'),
        )

        failures = list()
        for rule, failure_message in rules:
            if not rule:
                failures.append(failure_message)
        return failures

    def destroy(self):
        base_filepaths = self._generate_base_filepaths(keyring_root=self.__keyring_root)
        public_key_dir = base_filepaths['public_key_dir']
        private_key_dir = base_filepaths['private_key_dir']
        keypaths = self._generate_key_filepaths(account=self.checksum_address,
                                                public_key_dir=public_key_dir,
                                                private_key_dir=private_key_dir)

        # Remove the parsed paths from the disk, weather they exist or not.
        for filepath in keypaths.values():
            with contextlib.suppress(FileNotFoundError):
                os.remove(filepath)
