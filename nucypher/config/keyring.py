import json
import os
import stat
from base64 import urlsafe_b64encode
from typing import ClassVar

from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from cryptography.hazmat.primitives.kdf.scrypt import Scrypt
from eth_account import Account
from nacl.exceptions import CryptoError
from nacl.secret import SecretBox
from umbral.keys import UmbralPrivateKey

from nucypher.config.constants import DEFAULT_CONFIG_ROOT
from nucypher.config.node import NodeConfiguration
from nucypher.config.utils import validate_passphrase
from nucypher.crypto.powers import SigningPower, EncryptingPower, CryptoPower


def _parse_keyfile(keypath: str):
    """Parses a keyfile and returns key metadata as a dict."""

    with open(keypath, 'r') as keyfile:
        try:
            key_metadata = json.loads(keyfile)
        except json.JSONDecodeError:
            raise NodeConfiguration.ConfigurationError("Invalid data in keyfile {}".format(keypath))
        else:
            return key_metadata


def _save_private_keyfile(keypath: str, key_data: dict) -> str:
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
        keyfile_descriptor = os.open(file=keypath, flags=flags, mode=mode)
    finally:
        os.umask(0)  # Set the umask to 0 after opening

    # Write and destroy file descriptor reference
    with os.fdopen(keyfile_descriptor, 'wb') as keyfile:
        keyfile.write(json.dumps(key_data))
        output_path = keyfile.name

    # TODO: output_path is an integer, who knows why?
    del keyfile_descriptor
    return output_path


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
        keyfile_descriptor = os.open(file=keypath, flags=flags, mode=mode)
    finally:
        os.umask(0) # Set the umask to 0 after opening

    # Write and destroy the file descriptor reference
    with os.fdopen(keyfile_descriptor, 'wb') as keyfile:
        # key data should be urlsafe_base64
        keyfile.write(key_data)
        output_path = keyfile.name

    # TODO: output_path is an integer, who knows why?
    del keyfile_descriptor
    return output_path


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
        'nonce': urlsafe_b64encode(nonce).decode(),
        'enc_key': urlsafe_b64encode(enc_key).decode()
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
        raise  # TODO: Handle decryption failures

    umbral_key = UmbralPrivateKey.from_bytes(dec_key)
    return umbral_key


def _generate_encryption_keys() -> tuple:
    """Use pyUmbral keys to generate a new encrypting key pair"""
    privkey = UmbralPrivateKey.gen_key()
    pubkey = privkey.get_pubkey()
    return privkey, pubkey


def _generate_signing_keys() -> tuple:
    """
    TODO: Do we really want to use Umbral keys for signing?
    TODO: Perhaps we can use Curve25519/EdDSA for signatures?
    """
    privkey = UmbralPrivateKey.gen_key()
    pubkey = privkey.get_pubkey()
    return privkey, pubkey


def _generate_transacting_keys(passphrase: str) -> dict:
    """Create a new wallet address and private "transacting" key from the provided passphrase"""
    entropy = os.urandom(32)   # max out entropy for keccak256
    account = Account.create(extra_entropy=entropy)
    encrypted_wallet_data = Account.encrypt(private_key=account.privateKey, password=passphrase)
    return encrypted_wallet_data


class NucypherKeyring:
    """
    Warning: This class handles private keys!

    OS configuration and interface for ethereum and umbral keys

    Keyring filesystem tree
    ------------------------
    - keyring_root
        - .private
            - key.priv
        - public
            - key.pub

    """

    # TODO: Make lazy for better integration with config classes
    __default_keyring_root = os.path.join(DEFAULT_CONFIG_ROOT, "keyring")

    __default_public_key_dir = os.path.join(__default_keyring_root, 'public')
    __default_private_key_dir = os.path.join(__default_keyring_root, 'private')

    __default_key_filepaths = {
        'root': os.path.join(__default_private_key_dir, 'root_key.priv'),
        'root_pub': os.path.join(__default_public_key_dir, 'root_key.pub'),
        'signing': os.path.join(__default_private_key_dir, 'signing_key.priv'),
        'signing_pub': os.path.join(__default_public_key_dir, 'signing_key.pub'),
        'transacting': os.path.join(__default_private_key_dir, 'wallet.json'),
    }

    class KeyringError(Exception):
        pass

    class KeyringLocked(KeyringError):
        pass

    def __init__(self,
                 root_key_path: str=None,
                 pub_root_key_path: str=None,
                 signing_key_path: str=None,
                 pub_signing_key_path: str=None,
                 transacting_key_path: str=None) -> None:
        """
        Generates a NuCypherKeyring instance with the provided key paths,
        falling back to default keyring paths.
        """

        # Check for a custom private key or keyring root directory to use when locating keys
        self.__keyring_root = self.__default_keyring_root
        self.__private_key_dir = self.__default_private_key_dir

        # Check for any custom individual key paths
        self.__root_keypath = root_key_path or self.__default_key_filepaths['root']
        self.__signing_keypath = signing_key_path or self.__default_key_filepaths['signing']
        self.__transacting_keypath = transacting_key_path or self.__default_key_filepaths['transacting']

        # Check for any custom individual public key paths
        self.__root_pub_keypath = pub_root_key_path or self.__default_key_filepaths['root_pub']
        self.__signing_pub_keypath = pub_signing_key_path or self.__default_key_filepaths['signing_pub']

        # Setup key cache
        self.__derived_key_material = None
        self.__transacting_private_key = None

        # Check that the keyring is reflected on the filesystem
        for private_path in (self.__root_keypath, self.__signing_keypath, self.__transacting_keypath):
            pass

    def __del__(self):
        self.lock()

    def __decrypt_keyfile(self, key_path: str) -> UmbralPrivateKey:
        """Returns plaintext version of decrypting key."""

        # Checks for cached key
        if self.__derived_key_material is None:
            message = 'The keyring cannot be used when it is locked.  Call .unlock first.'
            raise self.KeyringLocked(message)

        key_data = _parse_keyfile(key_path)
        wrap_key = _derive_wrapping_key_from_key_material(key_data['wrap_salt'], self.__derived_key_material)
        plain_umbral_key = _decrypt_umbral_key(wrap_key, key_data['nonce'], key_data['enc_key'])

        return plain_umbral_key

    def unlock(self, passphrase: bytes) -> None:
        if self.__derived_key_material is not None:
            raise Exception('Keyring already unlocked')

        derived_key = _derive_key_material_from_passphrase(passphrase=passphrase)
        self.__derived_key_material = derived_key

    def lock(self) -> None:
        """Make efforts to remove references to the cached key data"""
        self.__derived_key_material = None
        self.__transacting_private_key = None

    def derive_crypto_power(self, power_class: ClassVar) -> CryptoPower:
        """
        Takes either a SigningPower or an EncryptingPower and returns
        a either a SigningPower or EncryptingPower with the coinciding
        private key.

        TODO: Derive a key from the root_key.
        TODO: TransactingPower
        """

        if power_class is SigningPower:
            key_path = self.__signing_keypath

        elif power_class is EncryptingPower:
            key_path = self.__root_keypath
        else:
            failure_message = "{} is an invalid type for deriving a CryptoPower.".format(type(power_class))
            raise ValueError(failure_message)

        umbral_privkey = self.__decrypt_keyfile(key_path)
        keypair = power_class._keypair_class(umbral_privkey)
        new_cryptopower = power_class(keypair=keypair)
        return new_cryptopower

    @classmethod
    def generate(cls,
                 passphrase: str,
                 encryption: bool = True,
                 transacting: bool = True,
                 output_path: str = None
                 ) -> 'NucypherKeyring':
        """
        Generates new encryption, signing, and transacting keys encrypted with the passphrase,
        respectively saving keyfiles on the local filesystem from *default* paths,
        returning the corresponding Keyring instance.
        """

        # Prepare and validate user input
        _private_key_dir = output_path if output_path else cls.__default_private_key_dir

        if not encryption and not transacting:
            raise ValueError('Either "encryption" or "transacting" must be True to generate new keys.')

        assert validate_passphrase(passphrase)

        # TODO
        # Ensure the configuration base directory exists
        # utils.generate_confg_dir()

        # Create the key directories with default paths. Raises OSError if dirs exist
        os.mkdir(cls.__default_public_key_dir, mode=0o744)  # public
        os.mkdir(_private_key_dir, mode=0o700)              # private

        # Generate keys
        keyring_args = dict()  # type: dict
        if encryption is True:
            enc_privkey, enc_pubkey = _generate_encryption_keys()
            sig_privkey, sig_pubkey = _generate_signing_keys()

            passphrase_salt = os.urandom(32)
            enc_salt = os.urandom(32)
            sig_salt = os.urandom(32)

            der_key_material = _derive_key_material_from_passphrase(passphrase_salt, passphrase)
            enc_wrap_key = _derive_wrapping_key_from_key_material(enc_salt, der_key_material)
            sig_wrap_key = _derive_wrapping_key_from_key_material(sig_salt, der_key_material)

            enc_json = _encrypt_umbral_key(der_key_material, enc_wrap_key)
            sig_json = _encrypt_umbral_key(der_key_material, sig_wrap_key)

            enc_json['master_salt'] = urlsafe_b64encode(enc_salt).decode()
            sig_json['master_salt'] = urlsafe_b64encode(sig_salt).decode()

            enc_json['wrap_salt'] = urlsafe_b64encode(enc_salt).decode()
            sig_json['wrap_salt'] = urlsafe_b64encode(sig_salt).decode()
            
            # Write private keys to files
            rootkey_path = _save_private_keyfile(cls.__default_key_filepaths['root'], enc_json)
            sigkey_path = _save_private_keyfile(cls.__default_key_filepaths['signing'], sig_json)

            bytes_enc_pubkey = enc_pubkey.to_bytes(encoder=urlsafe_b64encode)
            bytes_sig_pubkey = sig_pubkey.to_bytes(encoder=urlsafe_b64encode)

            # Write public keys to files
            rootkey_pub_path = _save_public_keyfile(
                cls.__default_key_filepaths['root_pub'],
                bytes_enc_pubkey
            )
            sigkey_pub_path = _save_public_keyfile(
                cls.__default_key_filepaths['signing_pub'],
                bytes_sig_pubkey
            )

            keyring_args.update(
                root_key_path=rootkey_path,
                pub_root_key_path=rootkey_pub_path,
                signing_key_path=sigkey_path,
                pub_signing_key_path=sigkey_pub_path
            )

        if transacting is True:
            wallet = _generate_transacting_keys(passphrase)
            _wallet_path = _save_private_keyfile(cls.__default_key_filepaths['transacting'], wallet)

            keyring_args.update(transacting_key_path=_wallet_path)

        # return an instance using the generated key paths
        keyring_instance = cls(**keyring_args)
        return keyring_instance
