import base64
import json
import os
import stat
from typing import ClassVar, Tuple, Callable, Union

from constant_sorrow import constants
from cryptography import x509
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.backends.openssl.ec import _EllipticCurvePrivateKey
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric.ec import EllipticCurve
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from cryptography.hazmat.primitives.kdf.scrypt import Scrypt
from cryptography.hazmat.primitives.serialization import Encoding
from cryptography.x509 import Certificate
from eth_account import Account
from eth_keys import KeyAPI as EthKeyAPI
from eth_utils import to_checksum_address
from nacl.exceptions import CryptoError
from nacl.secret import SecretBox
from umbral.keys import UmbralPrivateKey, UmbralPublicKey

from nucypher.config.constants import DEFAULT_CONFIG_ROOT
from nucypher.crypto.api import generate_self_signed_certificate
from nucypher.crypto.powers import SigningPower, EncryptingPower, CryptoPower, DelegatingPower, KeyPairBasedPower, \
    DerivedKeyBasedPower

#
# Constants
#

KEY_ENCODER = base64.urlsafe_b64encode
KEY_DECODER = base64.urlsafe_b64decode
KEY_FILE_ENCODING = 'utf-8'


#
# Utils
#

def validate_passphrase(passphrase) -> bool:
    """Validate a passphrase and return True or raise an error with a failure reason"""

    rules = (
        (bool(passphrase), 'Passphrase must not be blank.'),
        (len(passphrase) >= 16, 'Passphrase is too short, must be >= 16 chars.'),
    )

    for rule, failure_message in rules:
        if not rule:
            raise ValueError(failure_message)
    return True


def _read_keyfile(keypath: str, as_json=True, decode=True, decoder=KEY_DECODER):
    """Parses a json keyfile and returns deserialized key metadata as a dict."""
    with open(keypath, 'rb') as keyfile:
        try:
            raw_metadata = keyfile.read().decode()
            if as_json is True:
                key_metadata = json.loads(raw_metadata)
                if decode:
                    key_metadata = {field: decoder(value) for field, value in key_metadata.items()}
            else:
                key_metadata = raw_metadata
                if decode:
                    key_metadata = decoder(raw_metadata)
        except json.JSONDecodeError:
            raise RuntimeError("Invalid data in keyfile {}".format(keypath))
    return key_metadata


#
# Filesystem
#

def _save_private_keyfile(keypath: str,
                          key_data,
                          serialize: bool = True,
                          serializer: Callable = bytes,
                          encoding=KEY_FILE_ENCODING,
                          as_json: bool = False) -> str:
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

    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL    # Write, Create, Non-Existing
    mode = stat.S_IRUSR | stat.S_IWUSR              # 0o600

    try:
        keyfile_descriptor = os.open(keypath, flags=flags, mode=mode)
    finally:
        os.umask(0)  # Set the umask to 0 after opening

    # Encode as_json if requested, rebinding the reference
    if as_json is True:
        key_data = json.dumps(key_data)
    if serialize is True:
        key_data = serializer(key_data, encoding=encoding)

    # Write and destroy file descriptor reference
    with os.fdopen(keyfile_descriptor, 'wb') as keyfile:
        keyfile.write(key_data)

    # del keyfile_descriptor
    return keypath


def _save_public_keyfile(keypath: str, key_data: bytes) -> str:
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

    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL    # Write, Create, Non-Existing
    mode = stat.S_IRUSR | stat.S_IWUSR | stat.S_IRGRP | stat.S_IROTH  # 0o644

    try:
        keyfile_descriptor = os.open(keypath, flags=flags, mode=mode)
    finally:
        os.umask(0)  # Set the umask to 0 after opening

    # Write and destroy the file descriptor reference
    with os.fdopen(keyfile_descriptor, 'wb') as keyfile:
        # key data should be urlsafe_base64
        keyfile.write(key_data)

    del keyfile_descriptor
    return keypath


def _save_tls_certificate(certificate: Certificate,
                          full_filepath: str,
                          force: bool = False,
                          ) -> str:

    cert_already_exists = os.path.isfile(full_filepath)
    if force is False and cert_already_exists:
        raise FileExistsError('A TLS certificate already exists at {}.'.format(full_filepath))

    with open(full_filepath, 'wb') as certificate_file:
        public_pem_bytes = certificate.public_bytes(Encoding.PEM)
        certificate_file.write(public_pem_bytes)

    return full_filepath


def _load_tls_certificate(filepath: str) -> Certificate:
    """Deserialize an X509 certificate from a filepath"""
    try:
        with open(filepath, 'r') as certificate_file:
            cert = x509.load_pem_x509_certificate(certificate_file.read(),
                                                  backend=default_backend())
            return cert
    except FileNotFoundError:
        raise FileNotFoundError("No SSL certificate found at {}".format(filepath))


#
# Encrypt and Decrypt
#

def _derive_key_material_from_passphrase(salt: bytes, passphrase: str) -> bytes:
    """
    Uses Scrypt derivation to derive a  key for encrypting key material.
    See RFC 7914 for n, r, and p value selections.
    This takes around ~5 seconds to perform.
    """
    key_material = Scrypt(
        salt=salt,
        length=32,
        n=2**20,
        r=8,
        p=1,
        backend=default_backend()
    ).derive(passphrase.encode())

    return key_material


def _derive_wrapping_key_from_key_material(salt: bytes, key_material: bytes) -> bytes:
    """
    Uses HKDF to derive a 32 byte wrapping key to encrypt key material with.
    """
    wrapping_key = HKDF(
        algorithm=hashes.BLAKE2b(64),
        length=64,
        salt=salt,
        info=b'NuCypher-KeyWrap',
        backend=default_backend()
    ).derive(key_material)

    return wrapping_key[:32]


def _encrypt_umbral_key(wrapping_key: bytes, umbral_key: UmbralPrivateKey) -> dict:
    """
    Encrypts a key with nacl's XSalsa20-Poly1305 algorithm (SecretBox).
    Returns an encrypted key as bytes with the nonce appended.
    """
    nonce = os.urandom(24)
    enc_key = SecretBox(wrapping_key).encrypt(umbral_key.to_bytes(), nonce)
    crypto_data = {
        'nonce': nonce,
        'enc_key': bytes(enc_key.ciphertext)
    }
    return crypto_data


def _decrypt_umbral_key(wrapping_key: bytes,
                        nonce: bytes,
                        enc_key_material: bytes
                        ) -> UmbralPrivateKey:
    """
    Decrypts an encrypted key with nacl's XSalsa20-Poly1305 algorithm (SecretBox).
    Returns a decrypted key as an UmbralPrivateKey.
    """
    try:
        dec_key = SecretBox(wrapping_key).decrypt(enc_key_material, nonce)
    except CryptoError:
        raise

    umbral_key = UmbralPrivateKey.from_bytes(dec_key)
    return umbral_key


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


def _generate_wallet(passphrase: str) -> Tuple[str, dict]:
    """Create a new wallet address and private "transacting" key from the provided passphrase"""
    entropy = os.urandom(32)   # max out entropy for keccak256
    account = Account.create(extra_entropy=entropy)
    encrypted_wallet_data = Account.encrypt(private_key=account.privateKey, password=passphrase)
    return account.address, encrypted_wallet_data


def _generate_tls_keys(host: str, curve: EllipticCurve) -> Tuple[_EllipticCurvePrivateKey, Certificate]:
    cert, private_key = generate_self_signed_certificate(host, curve)
    return private_key, cert


class NucypherKeyring:
    """
    Handles keys for a single identity, recognized by account.
    Warning: This class handles private keys!

    Keyring filesystem tree
    ------------------------
    - keyring
        - .private
            - key.priv
            - key.priv.pem
        - public
            - key.pub
            - cert.pem

    """

    __default_keyring_root = os.path.join(DEFAULT_CONFIG_ROOT, 'keyring')

    class KeyringError(Exception):
        pass

    class KeyringLocked(KeyringError):
        pass

    def __init__(self,
                 account: str,
                 keyring_root: str = None,
                 root_key_path: str = None,
                 pub_root_key_path: str = None,
                 signing_key_path: str = None,
                 pub_signing_key_path: str = None,
                 wallet_path: str = None,
                 tls_key_path: str = None,
                 tls_certificate_path: str = None,
                 ) -> None:
        """
        Generates a NuCypherKeyring instance with the provided key paths falling back to default keyring paths.
        """

        self.__account = account
        self.__keyring_root = keyring_root or self.__default_keyring_root

        # Generate base filepaths
        __default_base_filepaths = self.generate_base_filepaths(keyring_root=self.__keyring_root)
        self.__public_key_dir = __default_base_filepaths['public_key_dir']
        self.__private_key_dir = __default_base_filepaths['private_key_dir']

        # Check for overrides
        __default_key_filepaths = self.generate_key_filepaths(account=self.__account,
                                                              public_key_dir=self.__public_key_dir,
                                                              private_key_dir=self.__private_key_dir)

        # Private
        self.__root_keypath = root_key_path or __default_key_filepaths['root']
        self.__signing_keypath = signing_key_path or __default_key_filepaths['signing']
        self.__wallet_path = wallet_path or __default_key_filepaths['wallet']
        self.__tls_keypath = tls_key_path or __default_key_filepaths['tls']

        # Public
        self.__root_pub_keypath = pub_root_key_path or __default_key_filepaths['root_pub']
        self.__signing_pub_keypath = pub_signing_key_path or __default_key_filepaths['signing_pub']
        self.__tls_certificate = tls_certificate_path or __default_key_filepaths['tls_certificate']

        # Set Initial State
        self.__derived_key_material = constants.KEYRING_LOCKED

    def __del__(self):
        self.lock()

    #
    # Public Keys
    #
    @property
    def checksum_address(self):
        key_data = _read_keyfile(keypath=self.__wallet_path, as_json=True, decode=False)
        address = key_data['address']
        return to_checksum_address(address)

    @property
    def federated_address(self):
        signature_pubkey = self.signing_public_key
        uncompressed_bytes = signature_pubkey.to_bytes(is_compressed=False)
        without_prefix = uncompressed_bytes[1:]
        verifying_key_as_eth_key = EthKeyAPI.PublicKey(without_prefix)
        address = verifying_key_as_eth_key.to_checksum_address()
        return address

    @property
    def signing_public_key(self):
        signature_pubkey_bytes = _read_keyfile(keypath=self.__signing_pub_keypath, as_json=False)
        signature_pubkey = UmbralPublicKey.from_bytes(signature_pubkey_bytes)
        return signature_pubkey

    @property
    def encrypting_public_key(self):
        encrypting_pubkey_bytes = _read_keyfile(keypath=self.__root_pub_keypath, as_json=False)
        encrypting_pubkey = UmbralPublicKey.from_bytes(encrypting_pubkey_bytes)
        return encrypting_pubkey

    @property
    def certificate_filepath(self):
        return self.__tls_certificate


    #
    # Utils
    #
    @staticmethod
    def generate_base_filepaths(keyring_root):
        base_paths = dict(public_key_dir=os.path.join(keyring_root, 'public'),
                          private_key_dir=os.path.join(keyring_root, 'private'))
        return base_paths

    @staticmethod
    def generate_key_filepaths(public_key_dir: str,
                               private_key_dir: str,
                               account: str) -> dict:
        __key_filepaths = {
            'root': os.path.join(private_key_dir, 'root-{}.priv'.format(account)),
            'root_pub': os.path.join(public_key_dir, 'root-{}.pub'.format(account)),
            'signing': os.path.join(private_key_dir, 'signing-{}.priv'.format(account)),
            'signing_pub': os.path.join(public_key_dir, 'signing-{}.pub'.format(account)),
            'wallet': os.path.join(private_key_dir, 'wallet-{}.json'.format(account)),
            'tls': os.path.join(private_key_dir, '{}.priv.pem'.format(account)),
            'tls_certificate': os.path.join(public_key_dir, '{}.pem'.format(account))
        }

        return __key_filepaths

    def _export_wallet_to_node(self, blockchain, passphrase):  # TODO: Deprecate with geth.parity signing EIPs
        """Decrypt the wallet with a passphrase, then import the key to the nodes's keyring over RPC"""
        with open(self.__wallet_path, 'rb') as wallet:
            data = wallet.read().decode(KEY_FILE_ENCODING)
            account = Account.decrypt(keyfile_json=data, password=passphrase)
            blockchain.interface.w3.personal.importRawKey(private_key=account, passphrase=passphrase)

    #
    # Access
    #
    def __decrypt_keyfile(self, key_path: str) -> UmbralPrivateKey:
        """Returns plaintext version of decrypting key."""

        # Checks for cached key
        if self.__derived_key_material is constants.KEYRING_LOCKED:
            raise self.KeyringLocked

        key_data = _read_keyfile(key_path)
        wrap_key = _derive_wrapping_key_from_key_material(salt=key_data['wrap_salt'],
                                                          key_material=self.__derived_key_material)
        plain_umbral_key = _decrypt_umbral_key(wrap_key,
                                               nonce=key_data['nonce'],
                                               enc_key_material=key_data['enc_key'])
        return plain_umbral_key

    def unlock(self, passphrase: bytes) -> None:
        if self.__derived_key_material is not constants.KEYRING_LOCKED:
            return

        key_data = _read_keyfile(keypath=self.__root_keypath, as_json=True)
        derived_key = _derive_key_material_from_passphrase(passphrase=passphrase, salt=key_data['master_salt'])
        self.__derived_key_material = derived_key

    def lock(self) -> None:
        """Make efforts to remove references to the cached key data"""
        self.__derived_key_material = constants.KEYRING_LOCKED

    def derive_crypto_power(self, power_class: ClassVar) -> Union[KeyPairBasedPower, DerivedKeyBasedPower]:
        """
        Takes either a SigningPower or an EncryptingPower and returns
        a either a SigningPower or EncryptingPower with the coinciding
        private key.

        TODO: Derive a key from the root_key.
        """
        # Keypair-Based
        if issubclass(power_class, KeyPairBasedPower):

            codex = {SigningPower: self.__signing_keypath,
                     EncryptingPower: self.__root_keypath
                     # BlockchainPower: self.__wallet_path,    # TODO
                     # TLSHostingPower: self.__tls_keypath}    # TODO
                     }

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
            new_cryptopower = power_class()

        else:
            failure_message = "{} is an invalid type for deriving a CryptoPower.".format(power_class.__name__)
            raise ValueError(failure_message)

        return new_cryptopower

    #
    # Create
    #
    @classmethod
    def generate(cls,
                 passphrase: str,
                 encrypting: bool = True,
                 wallet: bool = True,
                 tls: bool = True,
                 host: str = None,
                 curve = None,
                 keyring_root: str = None,
                 exists_ok: bool = True
                 ) -> 'NucypherKeyring':
        """
        Generates new encrypting, signing, and wallet keys encrypted with the passphrase,
        respectively saving keyfiles on the local filesystem from *default* paths,
        returning the corresponding Keyring instance.
        """

        validate_passphrase(passphrase)

        if not any((wallet, encrypting, tls)):
            raise ValueError('Either "encrypting", "wallet", or "tls" must be True '
                             'to generate new keys, or set "no_keys" to True to skip generation.')

        _base_filepaths = cls.generate_base_filepaths(keyring_root=keyring_root)
        _public_key_dir = _base_filepaths['public_key_dir']
        _private_key_dir = _base_filepaths['private_key_dir']

        # Create the key directories with default paths. Raises OSError if dirs exist
        # if exists_ok and not os.path.isdir(_public_key_dir):
        os.mkdir(_public_key_dir, mode=0o744)   # public dir

        # if exists_ok and not os.path.isdir(_private_key_dir):
        os.mkdir(_private_key_dir, mode=0o700)  # private dir

        #
        # Generate keys
        #

        keyring_args = dict()

        if wallet is True:
            new_address, new_wallet = _generate_wallet(passphrase)
            new_wallet_path = os.path.join(_private_key_dir, 'wallet-{}.json'.format(new_address))
            saved_wallet_path = _save_private_keyfile(new_wallet_path, new_wallet, as_json=True)
            keyring_args.update(wallet_path=saved_wallet_path)
            account = new_address

        if encrypting is True:
            enc_privkey, enc_pubkey = _generate_encryption_keys()
            sig_privkey, sig_pubkey = _generate_signing_keys()

            if not wallet:
                uncompressed_bytes = sig_pubkey.to_bytes(is_compressed=False)
                without_prefix = uncompressed_bytes[1:]
                verifying_key_as_eth_key = EthKeyAPI.PublicKey(without_prefix)
                account = verifying_key_as_eth_key.to_checksum_address()

        __key_filepaths = cls.generate_key_filepaths(account=account,
                                                     private_key_dir=_private_key_dir,
                                                     public_key_dir=_public_key_dir)
        if encrypting is True:
            passphrase_salt, enc_salt, sig_salt = os.urandom(32), os.urandom(32), os.urandom(32)
            der_key_material = _derive_key_material_from_passphrase(salt=passphrase_salt, passphrase=passphrase)
            enc_wrap_key = _derive_wrapping_key_from_key_material(salt=enc_salt, key_material=der_key_material)
            sig_wrap_key = _derive_wrapping_key_from_key_material(salt=sig_salt, key_material=der_key_material)

            enc_key_data = _encrypt_umbral_key(umbral_key=enc_privkey, wrapping_key=enc_wrap_key)
            sig_key_data = _encrypt_umbral_key(umbral_key=sig_privkey, wrapping_key=sig_wrap_key)

            def __encode_key_data(key_data: dict, master_salt: bytes, wrap_salt: bytes, encoder=KEY_ENCODER):
                encoded_key_data = {
                    'nonce': encoder(key_data['nonce']).decode(),
                    'enc_key': encoder(key_data['enc_key']).decode(),
                    'master_salt': encoder(master_salt).decode(),
                    'wrap_salt': encoder(wrap_salt).decode(),
                }
                return encoded_key_data

            enc_json = __encode_key_data(key_data=enc_key_data, master_salt=passphrase_salt, wrap_salt=enc_salt)
            sig_json = __encode_key_data(key_data=sig_key_data, master_salt=passphrase_salt, wrap_salt=sig_salt)

            # Write private keys to files
            rootkey_path = _save_private_keyfile(__key_filepaths['root'], enc_json, as_json=True, serialize=True)
            sigkey_path = _save_private_keyfile(__key_filepaths['signing'], sig_json, as_json=True, serialize=True)

            bytes_enc_pubkey = enc_pubkey.to_bytes(encoder=KEY_ENCODER)
            bytes_sig_pubkey = sig_pubkey.to_bytes(encoder=KEY_ENCODER)

            # Write public keys to files
            rootkey_pub_path = _save_public_keyfile(
                __key_filepaths['root_pub'],
                bytes_enc_pubkey
            )
            sigkey_pub_path = _save_public_keyfile(
                __key_filepaths['signing_pub'],
                bytes_sig_pubkey
            )

            keyring_args.update(
                keyring_root=keyring_root or cls.__default_keyring_root,
                root_key_path=rootkey_path,
                pub_root_key_path=rootkey_pub_path,
                signing_key_path=sigkey_path,
                pub_signing_key_path=sigkey_pub_path
            )

        if tls is True:
            if not all((host, curve)):
                raise ValueError("Host and curve are required to make a new keyring TLS certificate")
            private_key, cert = _generate_tls_keys(host, curve)

            def __save_key(pk, encoding):
                pem = pk.private_bytes(
                    encoding=encoding,
                    format=serialization.PrivateFormat.TraditionalOpenSSL,
                    encryption_algorithm=serialization.NoEncryption()
                )
                return pem

            tls_key_path = _save_private_keyfile(keypath=__key_filepaths['tls'],
                                                 key_data=private_key,
                                                 serialize=True,
                                                 serializer=__save_key,
                                                 encoding=serialization.Encoding.PEM,
                                                 as_json=False)

            certificate_filepath = _save_tls_certificate(full_filepath=__key_filepaths['tls_certificate'],
                                                         certificate=cert)

            keyring_args.update(tls_certificate_path=certificate_filepath,
                                tls_key_path=tls_key_path)

        # return an instance using the generated key paths
        keyring_instance = cls(account=account, **keyring_args)
        return keyring_instance
