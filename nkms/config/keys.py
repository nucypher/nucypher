import json
import os
from base64 import urlsafe_b64encode
from pathlib import Path

from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from cryptography.hazmat.primitives.kdf.scrypt import Scrypt
from eth_account import Account
from nacl.secret import SecretBox
from umbral.keys import UmbralPrivateKey
from web3.auto import w3

from nkms.crypto.powers import SigningPower, EncryptingPower, CryptoPower
from nkms.keystore.keypairs import SigningKeypair, EncryptingKeypair

w3.eth.enable_unaudited_features()

_CONFIG_ROOT = os.path.join(str(Path.home()), '.nucypher')


class KMSConfigurationError(RuntimeError):
    pass


def validate_passphrase(passphrase) -> str:
    """Validate a passphrase and return it or raise"""

    rules = (
        (len(passphrase) >= 16, 'Passphrase is too short, must be >= 16 chars.'),
    )

    for rule, failure_message in rules:
        if not rule:
            raise KMSConfigurationError(failure_message)
    else:
        return passphrase


def _derive_master_key_from_passphrase(salt: bytes, passphrase: str) -> bytes:
    """
    Uses Scrypt derivation to derive a master key for encrypting key material.
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


# TODO: Do we really want to use Umbral keys for signing?
# TODO: Perhaps we can use Curve25519/EdDSA for signatures?
def _generate_signing_keys() -> tuple:
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


def _save_keyfile(keypath: str, key_data: dict) -> None:
    """Saves key data to a file"""

    with open(keypath, 'w+') as keyfile:

        # Check_if the file is empty
        keyfile.seek(0)
        check_byte = keyfile.read(1)

        if len(check_byte) != 0:
            message = "{} is not empty. Check your key path.".format(keypath)
            raise KMSConfigurationError(message)

        # Write the keydata to the file
        keyfile.seek(0)
        keyfile.write(json.dumps(key_data))


def _generate_transacting_keys(passphrase: str) -> dict:
   """Create a new wallet address from the provided passphrase"""

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

    umbral_key = UmbralPrivateKey.from_bytes(plain_key)
    return umbral_key


def _get_signing_key(self, master_key: bytes = None) -> UmbralPrivateKey:
    """Returns plaintext version of private signature ("decrypting") key."""

    key_data = _parse_keyfile(self.__signing_keypath)

    # TODO: Prompt user for password?
    if master_key is None:
        return

    wrap_key = _derive_wrapping_key_from_master_key(key_data['wrap_salt'], master_key)
    plain_key = _decrypt_key(wrap_key, key_data['nonce'], key_data['enc_key'])

    umbral_key = UmbralPrivateKey.from_bytes(plain_key)
    return umbral_key


class KMSKeyring:
    """
    Warning: This class handles private keys!

    OS configuration and interface for ethereum and umbral keys

    Keyring filesystem tree
    ------------------------
    - keyring_root
        - .pub
        - keys
            - .priv

    """

    __keyring_root = _CONFIG_ROOT
    __default_public_key_dir = __keyring_root
    __default_private_key_dir = os.path.join(_CONFIG_ROOT, 'keys')  # Base Dir

    __default_keyring_paths = {
        'root_key': os.path.join(__default_private_key_dir, 'root_key.priv'),
        'signing_key': os.path.join(__default_private_key_dir, 'signing_key.priv'),
        'wallet': os.path.join(__default_private_key_dir, 'account.json')
    }

    def __init__(self, private_key_dir: str = None, root_keypath: str = None, signing_keypath: str = None,
                 wallet_keypath: str = None):

        # Check for a custom private key root directory
        self.__private_key_dir = private_key_dir or self.__default_private_key_dir

        # Check for any custom key paths
        self.__root_keypath = root_keypath or self.__default_keyring_paths['root_key']
        self.__signing_keypath = signing_keypath or self.__default_keyring_paths['signing_key']
        self.__wallet_keypath = wallet_keypath or self.__default_keyring_paths['wallet']

        # Key cache
        self.__derived_master_key = None
        self.__transacting_private_key = None

    def __del__(self):
        self.lock()

    # def _cache_transacting_key(self, passphrase) -> None:
    #     """Decrypts and caches an ethereum key"""
    #     key_data = _parse_keyfile(self.__wallet_keypath)
    #     hex_bytes_privkey = Account.decrypt(keyfile_json=key_data, password=passphrase)
    #     self.__transacting_privkey = hex_bytes_privkey

    def lock(self):
        self.__derived_master_key = None
        self.__transacting_private_key = None
        return

    def derive_crypto_power(self, power_class) -> CryptoPower:
        """
        Takes either a SigningPower or an EncryptingPower and returns
        a either a SigningPower or EncryptingPower with the coinciding
        private key.
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
    def from_keys(cls, config_root: str = None):
        """Generates a keyring object from existing keys on the local filesystem keys"""
        config_root = config_root or _CONFIG_ROOT
        pass

    @classmethod
    def _generate_default_keyring_tree(cls):
        os.mkdir(cls.__keyring_root)
        os.mkdir(cls.__k)

    @classmethod
    def generate(cls, passphrase, encryption=True, transacting=True):
        """
        Generates new encryption, signing, and transacting keys encrypted with the passphrase,
        respectively saving keyfiles on the local filesystem from default paths,
        returning the corresponding Keyring instance.
        """

        validate_passphrase(passphrase)

        if not encryption and not transacting:
            raise ValueError('Either "encryption" or "transacting" must be True to generate new keys.')

        if encryption is True:
            enc_key, _ = _generate_encryption_keys()
            sig_key, _ = _generate_signing_keys()

            salt = b'dead sea salt'  # TODO

            der_master_key = _derive_master_key_from_passphrase(salt, passphrase)
            der_wrap_key = _derive_wrapping_key_from_master_key(salt, der_master_key)

            enc_json = _encrypt_umbral_key(der_wrap_key, enc_key)
            sig_json = _encrypt_umbral_key(der_wrap_key, sig_key)

            enc_json['master_salt'] = urlsafe_b64encode(salt).decode()
            sig_json['master_salt'] = urlsafe_b64encode(salt).decode()

            enc_json['wrap_salt'] = urlsafe_b64encode(salt).decode()
            sig_json['wrap_salt'] = urlsafe_b64encode(salt).decode()

            _save_keyfile(cls.__default_keyring_paths['root_key'], enc_json)  # Write to file
            _save_keyfile(cls.__default_keyring_paths['signing_key'], sig_json)

        if transacting is True:
            wallet = _generate_transacting_keys(passphrase)
            _save_keyfile(cls.__default_keyring_paths['wallet'], wallet)

        keyring_instance = cls()  # all defaults
        return keyring_instance
