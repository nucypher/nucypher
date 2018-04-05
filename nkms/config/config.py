import json
import os

import web3
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from cryptography.hazmat.primitives.kdf.scrypt import Scrypt
from nacl.secret import SecretBox

import web3

from nkms.config.utils import _derive_wrapping_key_from_master_key, _decrypt_key


class EthAccount:
    """http://eth-account.readthedocs.io/en/latest/eth_account.html#eth-account"""

    def __init__(self, address):
        self.__address = address

    def __del__(self):
        self.lock()

    @property
    def address(self):
        return self.__address

    @classmethod
    def create(self, passphrase):
        """Create a new wallet address"""

    @classmethod
    def import_existing(self, private_key, passphrase):
        """Instantiate a wallet from an existing wallet address"""

    def unlock(self, passphrase, duration):
        """Unlock the account for a specified duration"""

    def lock(self):
        """Lock the account and make efforts to remove the key from memory"""

    def transact(self, txhash, passphrase):
        """Sign and transact without unlocking"""


class KMSConfig:
    """Warning: This class handles private keys!"""

    __config_root = os.path.join('~', '.nucypher')

    __default_yaml_path = os.path.join(__config_root, 'conf.yml')
    __keys_dir = os.path.join(__config_root, 'keys')
    __transacting_key_path = os.path.join('.ethereum')

    class KMSConfigurationError(Exception):
        pass

    def __init__(self, blockchain_address: str, keys_dir: str=None,
                 yaml_config_path: str=None):

        self.__config_path = config_path or self._default_config_path
        self.__enc_key_path = enc_key_path
        self.__sig_key_path = sig_key_path

        self.__yaml_config_path = yaml_config_path or self.__default_yaml_path
        self.__keys_dir = keys_dir

        # Blockchain
        self.address = blockchain_address

    @classmethod
    def from_yaml_config(cls, config_path=None):
        """Reads the config file and instantiates a KMSConfig instance"""

        with open(config_path or cls.__default_yaml_path, 'r') as conf_file:
            # Get data from the config file
            data = conf_file.read()    #TODO: Parse

        instance = cls()
        return instance

    def get_transacting_key(self, passphrase):
        with open(self.__transacting_key_path) as keyfile:
            encrypted_key = keyfile.read()
            private_key = web3.eth.account.decrypt(encrypted_key, passphrase)
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
        keyfile_path = os.path.join(self.__keys_dir, path)
        with open(keyfile_path, 'r') as keyfile:
            try:
                key_metadata = json.loads(keyfile)
            except json.JSONDecodeError:
                raise self.KMSConfigurationError("Invalid data in keyfile {}".format(path))
            else:
                return key_metadata

    def _save_keyfile(self, path: str, key_data: dict):
        """
        Saves key data to a file.
        """
        keyfile_path = os.path.join(self.__keys_dir, path)
        with open(keyfile_path, 'w+') as keyfile:
            keyfile.seek(0)
            check_byte = keyfile.read(1)
            if len(check_byte) != 0:
                raise self.KMSConfigurationError("Keyfile is not empty! Check your key path.")
            else:
                keyfile.seek(0)
                keyfile.write(json.dumps(key_data))

