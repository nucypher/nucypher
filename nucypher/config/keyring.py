import json
import os
import stat
from base64 import urlsafe_b64encode

from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from cryptography.hazmat.primitives.kdf.scrypt import Scrypt
from eth_account import Account
from nacl.exceptions import CryptoError
from nacl.secret import SecretBox
from typing import ClassVar, Tuple
from umbral.keys import UmbralPrivateKey

from nucypher.config.constants import DEFAULT_CONFIG_ROOT
from nucypher.config.node import NodeConfiguration
from nucypher.crypto.powers import SigningPower, EncryptingPower, CryptoPower


def validate_passphrase(passphrase) -> bool:
    """Validate a passphrase and return True or raise an error with a failure reason"""

    rules = (
        (len(passphrase) >= 16, 'Passphrase is too short, must be >= 16 chars.'),
    )

    for rule, failure_message in rules:
        if not rule:
            raise NodeConfiguration.ConfigurationError(failure_message)
    return True


def _parse_keyfile(keypath: str):
    """Parses a keyfile and returns key metadata as a dict."""

    with open(keypath, 'rb') as keyfile:
        try:
            key_metadata = json.loads(keyfile.read())
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
        keyfile_descriptor = os.open(keypath, flags=flags, mode=mode)
    finally:
        os.umask(0)  # Set the umask to 0 after opening

    # Write and destroy file descriptor reference
    with os.fdopen(keyfile_descriptor, 'wb') as keyfile:
        keyfile.write(bytes(json.dumps(key_data), encoding='utf-8'))

    del keyfile_descriptor
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


def _generate_wallet(passphrase: str) -> Tuple[str, dict]:
    """Create a new wallet address and private "transacting" key from the provided passphrase"""
    entropy = os.urandom(32)   # max out entropy for keccak256
    account = Account.create(extra_entropy=entropy)
    encrypted_wallet_data = Account.encrypt(private_key=account.privateKey, password=passphrase)
    return account.address, encrypted_wallet_data


class NucypherKeyring:
    """
    Handles keys for a single __common_name.

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

    __default_keyring_root = os.path.join(DEFAULT_CONFIG_ROOT, 'keyring')
    __default_public_key_dir = os.path.join(__default_keyring_root, 'public')
    __default_private_key_dir = os.path.join(__default_keyring_root, 'private')

    class KeyringError(Exception):
        pass

    class KeyringLocked(KeyringError):
        pass

    def __init__(self,
                 common_name: str,
                 keyring_root: str = None,
                 public_key_dir: str = None,
                 private_key_dir: str = None,
                 root_key_path: str = None,
                 pub_root_key_path: str = None,
                 signing_key_path: str = None,
                 pub_signing_key_path: str = None,
                 wallet_path: str = None,
                 tls_key_path: str = None) -> None:
        """
        Generates a NuCypherKeyring instance with the provided key paths,
        falling back to default keyring paths.
        """

        self.__common_name = common_name

        # Check for a custom private key or keyring root directory to use when locating keys
        self.__keyring_root = keyring_root or self.__default_keyring_root
        self.__public_key_dir = public_key_dir or self.__default_public_key_dir
        self.__private_key_dir = private_key_dir or self.__default_private_key_dir

        __key_filepaths = self.generate_filepaths(common_name=self.__common_name,
                                                  public_key_dir=self.__public_key_dir,
                                                  private_key_dir=self.__private_key_dir)

        # Check for any custom individual key paths
        self.__root_keypath = root_key_path or __key_filepaths['root']
        self.__signing_keypath = signing_key_path or __key_filepaths['signing']
        self.__wallet_path = wallet_path or __key_filepaths['wallet']
        self.__tls_keypath = tls_key_path or __key_filepaths['tls']

        # Check for any custom individual public key paths
        self.__root_pub_keypath = pub_root_key_path or __key_filepaths['root_pub']
        self.__signing_pub_keypath = pub_signing_key_path or __key_filepaths['signing_pub']

        # Setup key cache
        self.__derived_key_material = None
        self.__transacting_private_key = None

    def __del__(self):
        self.lock()

    @property
    def transacting_public_key(self):
        wallet = _parse_keyfile(keypath=self.__wallet_path)
        return wallet['address']

    @staticmethod
    def generate_filepaths(public_key_dir: str,
                           private_key_dir: str,
                           common_name: str) -> dict:

        __key_filepaths = {
            'root': os.path.join(private_key_dir, 'root-{}.priv'.format(common_name)),
            'root_pub': os.path.join(public_key_dir, 'root-{}.pub'.format(common_name)),
            'signing': os.path.join(private_key_dir, 'signing-{}.priv'.format(common_name)),
            'signing_pub': os.path.join(public_key_dir, 'signing-{}.pub'.format(common_name)),
            'wallet': os.path.join(private_key_dir, 'wallet-{}.json'.format(common_name)),
            'tls': os.path.join(private_key_dir, '{}.pem'.format(common_name))
        }

        return __key_filepaths

    def _export(self, blockchain, passphrase):
        with open(self.__wallet_path, 'rb') as wallet:
            data = wallet.read().decode('utf-8')
            account = Account.decrypt(keyfile_json=data, password=passphrase)
            blockchain.interface.w3.personal.importRawKey(private_key=account, passphrase=passphrase)

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

        # TODO: missing salt parameter below
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
                 encrypting: bool = True,
                 wallet: bool = True,
                 public_key_dir: str = None,
                 private_key_dir: str = None,
                 keyring_root: str = None,
                 ) -> 'NucypherKeyring':
        """
        Generates new encrypting, signing, and wallet keys encrypted with the passphrase,
        respectively saving keyfiles on the local filesystem from *default* paths,
        returning the corresponding Keyring instance.
        """

        # Prepare and validate user input
        _public_key_dir = public_key_dir if public_key_dir else cls.__default_public_key_dir
        _private_key_dir = private_key_dir if private_key_dir else cls.__default_private_key_dir

        if not encrypting and not wallet:
            raise ValueError('Either "encrypting" or "wallet" must be True to generate new keys.')

        validate_passphrase(passphrase)

        # Create the key directories with default paths. Raises OSError if dirs exist
        os.mkdir(_public_key_dir, mode=0o744)  # public()
        os.mkdir(_private_key_dir, mode=0o700) # private

        # Generate keys
        keyring_args = dict()

        if wallet is True:
            new_address, new_wallet = _generate_wallet(passphrase)
            new_wallet_path = os.path.join(_private_key_dir, 'wallet-{}.json'.format(new_address))
            saved_wallet_path = _save_private_keyfile(new_wallet_path, new_wallet)
            keyring_args.update(wallet_path=saved_wallet_path)

        if encrypting is True:
            enc_privkey, enc_pubkey = _generate_encryption_keys()
            sig_privkey, sig_pubkey = _generate_signing_keys()

        if wallet:          # common name router, prefer checksum address
            common_name = new_address
        elif encrypting:
            common_name = sig_pubkey

        __key_filepaths = cls.generate_filepaths(public_key_dir=_public_key_dir,
                                                 private_key_dir=_private_key_dir,
                                                 common_name=common_name)

        if encrypting is True:
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
            rootkey_path = _save_private_keyfile(__key_filepaths['root'], enc_json)
            sigkey_path = _save_private_keyfile(__key_filepaths['signing'], sig_json)

            bytes_enc_pubkey = enc_pubkey.to_bytes(encoder=urlsafe_b64encode)
            bytes_sig_pubkey = sig_pubkey.to_bytes(encoder=urlsafe_b64encode)

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

        # return an instance using the generated key paths
        keyring_instance = cls(common_name=common_name, **keyring_args)
        return keyring_instance
