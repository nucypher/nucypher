import base64
import os

import web3
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from cryptography.hazmat.primitives.kdf.scrypt import Scrypt
from nacl.secret import SecretBox


class Wallet:
    def accounts(self):
        return web3.personal.listAccounts()

    @classmethod
    def create(self):
        pass

    @classmethod
    def import_existing(self):
        pass


class KMSConfig:
    """Warning: This class handles private keys!"""

    _default_config_path = None
    __root_name = '.nucypher'
    __default_key_dir = os.path.join('~', __root_name, 'keys')    # TODO: Change by actor

    class KMSConfigrationError(Exception):
        pass

    def __init__(self, blockchain_address: str, enc_key_path: str=None,
                 sig_key_path: str=None, config_path: str=None):

        if self._default_config_path is None:
            pass    # TODO: no default config path set

        self.__config_path = config_path or self._default_config_path
        self.__enc_key_path = enc_key_path
        self.__sig_key_path = sig_key_path

        # Blockchain
        self.address = blockchain_address

    @classmethod
    def from_config_file(cls, config_path=None):
        """Reads the config file and instantiates a KMSConfig instance"""
        with open(config_path or cls._default_config_path, 'r') as f:
            # Get data from the config file
            data = f.read()    #TODO: Parse

        instance = cls()
        return instance

    def get_transacting_key(self):
        """

        """
        with open(self.transacting_key_path) as keyfile:
            encrypted_key = keyfile.read()
            private_key = web3.eth.account.decrypt(encrypted_key, 'correcthorsebatterystaple')
            # WARNING: do not save the key or password anywhere

    def get_decrypting_key(self, master_key: bytes=None):
        """
        Returns plaintext version of decrypting key.
        """
        key_data = self._parse_keyfile('root_key.priv')

        # TODO: Prompt user for password?
        if not master_key:
            return

        wrap_key = _derive_wrapping_key_from_master_key(
            key_data['wrap_salt'], master_key)

        plain_key = _decrypt_key(wrap_key, key_data['nonce'], key_data['enc_key'])
        return plain_key

    def get_signing_key(self, master_key: bytes=None):
        """
        Returns plaintext version of decrypting key.
        """
        key_data = self._parse_keyfile('signing_key.priv')

        # TODO: Prompt user for password?
        if not master_key:
            return

        wrap_key = _derive_wrapping_key_from_master_key(
            key_data['wrap_salt'], master_key)

        plain_key = _decrypt_key(wrap_key, key_data['nonce'], key_data['enc_key'])
        return plain_key

    def _parse_keyfile(self, path: str):
        """
        Parses a keyfile and returns key metadata as a dict.
        """
        keyfile_path = os.path.join(self.__key_dir, path)
        with open(keyfile_path, 'r') as keyfile:
            try:
                key_metadata = json.loads(keyfile)
        except json.JSONDecodeError:
            raise KMSConfigurationError("Invalid data in keyfile {}".format(path))

        return key_metadata

    def _save_keyfile(self, path: str, key_data: dict):
        """
        Saves key data to a file.
        """
        keyfile_path = os.path.join(self.__key_dir, path)
        with open(keyfile_path),  'w+') as keyfile:
            f.seek(0)
            check_byte = keyfile.read(1)
            if len(check_byte) != 0:
                raise self.KMSConfigurationError("Keyfile is not empty! Check your key path.")
            else:
                keyfile.seek(0)
                keyfile.write(json.dumps(key_data))


def _derive_master_key_from_passphrase(salt: bytes, passphrase: str):
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


def _derive_wrapping_key_from_master_key(salt: bytes, master_key: bytes):
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


def _encrypt_key(wrapping_key: bytes, key_material: bytes):
    """
    Encrypts a key with nacl's XSalsa20-Poly1305 algorithm (SecretBox).
    Returns an encrypted key as bytes with the nonce appended.
    """
    nonce = os.urandom(24)
    enc_key = SecretBox(wrapping_key).encrypt(key_material, nonce)

    crypto_data = {
        'nonce': nonce,
        'enc_key': enc_key
    }

    return crypto_data


# TODO: Handle decryption failures
def _decrypt_key(wrapping_key: bytes, nonce: bytes, enc_key_material: bytes):
    """
    Decrypts an encrypted key with nacl's XSalsa20-Poly1305 algorithm (SecretBox).
    Returns a decrypted key as bytes.
    """
    dec_key = SecretBox(wrapping_key).encrypt(enc_key_material, nonce)

    return dec_key


def _generate_encryption_keys():
    privkey = UmbralPrivateKey.gen_key()
    pubkey = priv_key.get_pubkey()

    return (privkey, pubkey)


# TODO: Do we really want to use Umbral keys for signing?
# TODO: Perhaps we can use Curve25519/EdDSA for signatures?
def _generate_signing_keys():
    privkey = UmbralPrivateKey.gen_key()
    pubkey = priv_key.get_pubkey()

    return (privkey, pubkey)
