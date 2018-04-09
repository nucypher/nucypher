import errno
import json
import os
import stat
from base64 import urlsafe_b64encode
from pathlib import Path
from typing import ClassVar

from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from cryptography.hazmat.primitives.kdf.scrypt import Scrypt
from eth_account import Account
from nacl.secret import SecretBox
from umbral.keys import UmbralPrivateKey
from web3.auto import w3

from nkms.config import utils
from nkms.config.configs import _DEFAULT_CONFIGURATION_DIR, KMSConfigurationError
from nkms.crypto.powers import SigningPower, EncryptingPower, CryptoPower
from nkms.keystore.keypairs import SigningKeypair, EncryptingKeypair

w3.eth.enable_unaudited_features()

_CONFIG_ROOT = os.path.join(str(Path.home()), '.nucypher')


class KMSConfigurationError(RuntimeError):
    pass


def validate_passphrase(passphrase) -> bool:
    """Validate a passphrase and return True or raise an error with a failure reason"""

    rules = (
        (len(passphrase) >= 16, 'Passphrase is too short, must be >= 16 chars.'),
    )

    for rule, failure_message in rules:
        if not rule:
            raise KMSConfigurationError(failure_message)
    return True


def _derive_master_key_from_passphrase(salt: bytes, passphrase: str) -> bytes:
    """
    Uses Scrypt derivation to derive a  key for encrypting key material.
    See RFC 7914 for n, r, and p value selections.
    This takes around ~5 seconds to perform.
    """
    master_key = Scrypt(
        salt=salt,
        length=32,
        n=2**20,
        r=8,
        p=1,
        backend=default_backend()
    ).derive(passphrase.encode())

    return master_key


def _derive_wrapping_key_from_master_key(salt: bytes, master_key: bytes) -> bytes:
    """
    Uses HKDF to derive a 32 byte wrapping key to encrypt key material with.
    """
    wrapping_key = HKDF(
        algorithm=hashes.SHA512(),
        length=32,
        salt=salt,
        info=b'NuCypher-KMS-KeyWrap',
        backend=default_backend()
    ).derive(master_key)

    return wrapping_key


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


# TODO: Handle decryption failures
def _decrypt_key(wrapping_key: bytes, nonce: bytes, enc_key_material: bytes) -> UmbralPrivateKey:
    """
    Decrypts an encrypted key with nacl's XSalsa20-Poly1305 algorithm (SecretBox).
    Returns a decrypted key as an UmbralPrivateKey.
    """
    dec_key = SecretBox(wrapping_key).encrypt(enc_key_material, nonce)
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


def _parse_keyfile(keypath: str):
    """Parses a keyfile and returns key metadata as a dict."""

    with open(keypath, 'r') as keyfile:
        try:
            key_metadata = json.loads(keyfile)
        except json.JSONDecodeError:
            raise KMSConfigurationError("Invalid data in keyfile {}".format(keypath))
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
        keyfile_descriptor = os.open(path=keypath, flags=flags, mode=mode)
    finally:
        os.umask(0)  # Set the umask to 0 after opening

    # Write and destroy file descriptor reference
    with os.fdopen(keyfile_descriptor, 'w') as keyfile:
        keyfile.write(json.dumps(key_data))
        output_path = keyfile.name

    del keyfile_descriptor
    return output_path


def _generate_transacting_keys(passphrase: str) -> dict:
    """Create a new wallet address and private "transacting" key from the provided passphrase"""
    entropy = os.urandom(32)   # max out entropy for keccak256
    account = Account.create(extra_entropy=entropy)
    encrypted_wallet_data = Account.encrypt(private_key=account.privateKey, password=passphrase)
    return encrypted_wallet_data


# TODO: Make these one function
def _get_decrypting_key(self, master_key: bytes = None) -> UmbralPrivateKey:
    """Returns plaintext version of decrypting key."""

    key_data = _parse_keyfile(self.__private_key_dir)

    # TODO: Prompt user for password?
    if master_key is None:
        return

    wrap_key = _derive_wrapping_key_from_master_key(key_data['wrap_salt'], master_key)
    plain_key = _decrypt_key(wrap_key, key_data['nonce'], key_data['enc_key'])

    return plain_key


def _get_signing_key(self, master_key: bytes = None) -> UmbralPrivateKey:
    """Returns plaintext version of private signature ("decrypting") key."""

    key_data = _parse_keyfile(self.__signing_keypath)

    # TODO: Prompt user for password?
    if master_key is None:
        return

    wrap_key = _derive_wrapping_key_from_master_key(key_data['wrap_salt'], master_key)
    plain_key = _decrypt_key(wrap_key, key_data['nonce'], key_data['enc_key'])

    return plain_key


class KMSKeyring:
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

    __default_keyring_root = os.path.join(_DEFAULT_CONFIGURATION_DIR, 'keyring')

    __default_public_key_dir = os.path.join(__default_keyring_root, 'public')
    __default_private_key_dir = os.path.join(__default_keyring_root, 'private')

    __default_key_filepaths = {
        'root': os.path.join(__default_private_key_dir, 'root_key.priv'),
        'signing': os.path.join(__default_private_key_dir, 'signing_key.priv'),
        'transacting': os.path.join(__default_private_key_dir, 'wallet.json')
    }

    def __init__(self, root_key_path: str=None, signing_key_path: str=None, transacting_key_path: str=None):
        """
        Generates a KMSKeyring instance with the provided key paths,
        falling back to default keyring paths.
        """

        # Check for a custom private key or keyring root directory to use when locating keys
        self.__keyring_root = self.__default_keyring_root
        self.__private_key_dir = self.__default_private_key_dir

        # Check for any custom individual key paths
        self.__root_keypath = root_key_path or self.__default_key_filepaths['root']
        self.__signing_keypath = signing_key_path or self.__default_key_filepaths['signing']
        self.__transacting_keypath = transacting_key_path or self.__default_key_filepaths['transacting']

        # Setup key cache
        self.__derived_master_key = None
        self.__transacting_private_key = None

        # Check that the keyring is reflected on the filesystem
        for private_path in (self.__root_keypath, self.__signing_keypath, self.__transacting_keypath):
            pass

    def __del__(self):
        self.lock()

    def lock(self) -> None:
        self.__derived_master_key = None
        self.__transacting_private_key = None

    def derive_crypto_power(self, power_class: ClassVar) -> CryptoPower:
        """
        Takes either a SigningPower or an EncryptingPower and returns
        a either a SigningPower or EncryptingPower with the coinciding
        private key.

        TODO: TransactingPower
        """
        if power_class is SigningPower:
            umbral_privkey = _get_signing_key(self.__derived_master_key)
            keypair = SigningKeypair(umbral_privkey)

        elif power_class is EncryptingPower:
            # TODO: Derive a key from the root_key.
            umbral_privkey = _get_decrypting_key(self.__derived_master_key)
            keypair = EncryptingKeypair(umbral_privkey)

        else:
            failure_message = "{} is an invalid type for deriving a CryptoPower.".format(type(power_class))
            raise ValueError(failure_message)

        new_power = power_class(keypair=keypair)
        return new_power

    @classmethod
    def generate(cls, passphrase: str, encryption: bool=True, transacting: bool=True, output_path: str=None) -> 'KMSKeyring':
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

        # Ensure the configuration base directory exists
        utils.generate_confg_dir()

        # Create the key directories with default paths. Raises OSError if dirs exist
        os.mkdir(cls.__default_keyring_root, mode=0o755)    # keyring
        os.mkdir(cls.__default_public_key_dir, mode=0o744)  # public
        os.mkdir(_private_key_dir, mode=0o744)              # private

        # Generate keys
        keyring_args = dict()
        if encryption is True:
            enc_key, _ = _generate_encryption_keys()
            sig_key, _ = _generate_signing_keys()

            salt = os.urandom(32)

            der_master_key = _derive_master_key_from_passphrase(salt, passphrase)
            der_wrap_key = _derive_wrapping_key_from_master_key(salt, der_master_key)

            enc_json = _encrypt_umbral_key(der_wrap_key, enc_key)
            sig_json = _encrypt_umbral_key(der_wrap_key, sig_key)

            enc_json['master_salt'] = urlsafe_b64encode(salt).decode()
            sig_json['master_salt'] = urlsafe_b64encode(salt).decode()

            enc_json['wrap_salt'] = urlsafe_b64encode(salt).decode()
            sig_json['wrap_salt'] = urlsafe_b64encode(salt).decode()

            rootkey_path = _save_private_keyfile(cls.__default_key_filepaths['root'], enc_json)  # Write to file
            sigkey_path = _save_private_keyfile(cls.__default_key_filepaths['signing'], sig_json)

            keyring_args.update(root_key_path=rootkey_path, signing_key_path=sigkey_path)

        if transacting is True:
            wallet = _generate_transacting_keys(passphrase)
            _wallet_path = _save_private_keyfile(cls.__default_key_filepaths['transacting'], wallet)

            keyring_args.update(transacting_key_path=_wallet_path)

        # return an instance using the generated key paths
        keyring_instance = cls(**keyring_args)
        return keyring_instance
