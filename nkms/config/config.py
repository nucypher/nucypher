import base64
import os

import web3


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

    def get_decrypting_key(self):
        pass

    def get_signing_key(self):
        pass


def _encode_keys(self, encoder=base64.b64encode, *keys):
    data = sum(keys)
    encoded = encoder(data)
    return encoded    # TODO: Validate


def _save_keyfile(self, encoded_keys):
    """Check if the keyfile is empty, then write."""

    with open(self.__key_path, 'w+') as f:
        f.seek(0)
        check_byte = f.read(1)
        if check_byte != '':
            raise self.KMSConfigrationError("Keyfile is not empty! Check your key path.")
        f.seek(0)
        f.write(encoded_keys.decode())


def _generate_encryption_keys(self):
    privkey = UmbralPrivateKey.gen_key()
    pubkey = priv_key.get_pubkey()

    return (privkey, pubkey)


# TODO: Do we really want to use Umbral keys for signing?
# TODO: Perhaps we can use Curve25519/EdDSA for signatures?
def _generate_signing_keys(self):
    privkey = UmbralPrivateKey.gen_key()
    pubkey = priv_key.get_pubkey()

    return (privkey, pubkey)
