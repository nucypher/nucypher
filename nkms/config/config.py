import os
from pathlib import Path

from eth_account import Account
from umbral.keys import UmbralPrivateKey
from web3.auto import w3


from nkms.config.utils import _derive_wrapping_key_from_master_key, _decrypt_key
from nkms.crypto.powers import SigningPower, EncryptingPower
from nkms.keystore.keypairs import SigningKeypair, EncryptingKeypair

_CONFIG_ROOT = os.path.join(str(Path.home()), '.nucypher')


class KMSKeyring:
    """Warning: This class handles private keys!"""

    __privkey_dir = os.path.join(_CONFIG_ROOT, 'keys')
    __root_keypath = os.path.join(__privkey_dir, 'root_key.priv')
    __signing_keypath = os.path.join(__privkey_dir, 'signing_key.priv')
    __transacting_keypath = os.path.join(__privkey_dir, 'signing_key.priv')

    __derived_master_key = None
    __transacting_privkey = None

    def __init__(self, key_root: str=None):
        self.__privkey_dir = key_root

    # TODO: Make these one function
    def __get_decrypting_key(self, master_key: bytes=None) -> UmbralPrivateKey:
        """Returns plaintext version of decrypting key."""

        key_data = utils._parse_keyfile(self.__privkey_dir)

        # TODO: Prompt user for password?
        if not master_key:
            return

        wrap_key = _derive_wrapping_key_from_master_key(key_data['wrap_salt'], master_key)
        plain_key = _decrypt_key(wrap_key, key_data['nonce'], key_data['enc_key'])

        umbral_key = UmbralPrivateKey.from_bytes(plain_key)
        return umbral_key

    def __get_signing_key(self, master_key: bytes=None) -> UmbralPrivateKey:
        """Returns plaintext version of private signature ("decrypting") key."""

        key_data = utils._parse_keyfile(self.__signing_keypath)

        # TODO: Prompt user for password?
        if not master_key:
            return

        wrap_key = _derive_wrapping_key_from_master_key(key_data['wrap_salt'], master_key)
        plain_key = _decrypt_key(wrap_key, key_data['nonce'], key_data['enc_key'])

        umbral_key = UmbralPrivateKey.from_bytes(plain_key)
        return umbral_key

    def _cache_transacting_key(self, passphrase) -> None:
        """Decrypts and caches an ethereum key"""
        key_data = utils._parse_keyfile(self.__transacting_keypath)
        hex_bytes_privkey = Account.decrypt(keyfile_json=key_data, password=passphrase)
        self.__transacting_privkey = hex_bytes_privkey

    def lock_wallet(self) -> None:
        self.__transacting_privkey = None

    def lock_master_key(self) -> None:
        self.__derived_master_key = None

    def derive_crypto_power(self, power_class):
        """
        Takes either a SigningPower or an EncryptingPower and returns
        a either a SigningPower or EncryptingPower  with the coinciding
        private key.
        """
        if power_class is SigningPower:
            umbral_privkey = self.__get_signing_key(self.__derived_master_key)
            keypair = SigningKeypair(umbral_privkey)

        elif power_class is EncryptingPower:
            # TODO: Derive a key from the root_key.
            umbral_privkey = self.__get_decrypting_key(self.__derived_master_key)
            keypair = EncryptingKeypair(umbral_privkey)

        else:
            raise ValueError("Invalid class for deriving a power.")

        new_power = power_class(keypair=keypair)
        return new_power


class Wallet:
    """http://eth-account.readthedocs.io/en/latest/eth_account.html#eth-account"""

    def __init__(self, address: str, keyring: KMSKeyring):
        self.__address = address
        self.keyring = keyring

        self.__transacting_key = None

    def __del__(self):
        self.lock()

    @property
    def address(self) -> str:
        return self.__address

    def unlock(self, passphrase) -> None:
        """Unlock the account indefinately"""
        self.keyring._cache_transacting_key(passphrase)

    def lock(self) -> None:
        """Lock the account and make efforts to remove the key from memory"""
        self.keyring.lock_wallet()

    def transact(self, transaction, passphrase) -> str:
        """
        Sign and transact without unlocking.
        https://web3py.readthedocs.io/en/stable/web3.eth.account.html#sign-a-contract-transaction
        """
        signed_txn = w3.eth.account.signTransaction(transaction, private_key=self.__transacting_key)
        txhash = w3.eth.sendRawTransaction(signed_txn.rawTransaction)
        return txhash


class Stake:
    def __init__(self, amount: int, duration: int, start):
        self.amount = amount
        self.duration = duration
        self.start_datetime = start
        # self.end_date = datetime.utcnow()


class PolicyConfig:
    def __init__(self, default_m: int, default_n: int, gas_limit: int):
        self.default_m = default_m
        self.default_n = default_n
        self.gas_limit = gas_limit


class KMSConfig:
    """
    Configuration class providing access to Ethereum accounts and NuCypher KMS secret keys
    """

    class KMSConfigurationError(RuntimeError):
        pass

    __default_config_filepath = os.path.join(_CONFIG_ROOT, 'conf.yml')
    __default_db_path = os.path.join(_CONFIG_ROOT, 'kms_datastore.db')

    def __init__(self,
                 wallet: 'Wallet',
                 keyring: 'KMSKeyring',
                 policy_config: PolicyConfig,
                 stake_config: Stake=None,
                 db_path: str=None,
                 config_filepath: str=None):

        self.__config_filepath = config_filepath or self.__default_config_filepath
        self.__db_path = db_path or self.__default_db_path    # Sqlite

        self.keyring = keyring
        self.wallet = wallet
        self.stake_confg = stake_config
        self.policy_config = policy_config

    @property
    def db_path(self):
        return self.__db_path

    @classmethod
    def get_config(cls):
        """Gets the current config"""

    @classmethod
    def from_config_file(cls, config_path=None):
        """Reads the config file and creates a KMSConfig instance"""
