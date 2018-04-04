import base64

from nkms.crypto import api as API


class KMSConfig:
    """
    Warning: This class handles private keys!

    """

    _default_config_path = None

    class KMSConfigrationError(Exception):
        pass

    def __init__(self, blockchain_address: str, key_path: str=None, config_path: str=None):

        if self._default_config_path is None:
            pass    # TODO: no default config path set

        self.__config_path = config_path or self._default_config_path
        self.__key_path = key_path

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
        pass

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
    ecies_privkey = API.ecies_gen_priv(to_bytes=True)
    ecies_pubkey = API.ecies_priv2pub(ecies_privkey, to_bytes=True)

    return ecies_privkey, ecies_pubkey


def _generate_signing_keys(self):
    ecdsa_privkey = API.ecdsa_gen_priv()
    ecdsa_pubkey = API.ecdsa_priv2pub(ecdsa_privkey, to_bytes=True)

    return ecdsa_privkey, ecdsa_pubkey
