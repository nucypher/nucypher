import json
import os
from pathlib import Path

_DEFAULT_CONFIGURATION_DIR = os.path.join(str(Path.home()), '.nucypher')


class KMSConfigurationError(RuntimeError):
    pass


class StakeConfig:
    def __init__(self, amount: int, periods: int, start_datetime):
        self.amount = amount
        self.periods = periods
        self.start = start_datetime


class PolicyConfig:
    def __init__(self, default_m: int, default_n: int, gas_limit: int):
        self.prefered_m = default_m
        self.prefered_n = default_n
        self.transaction_gas_limit = gas_limit


class NetworkConfig:
    __default_db_name = 'kms_datastore.db'
    __default_db_path = os.path.join(_DEFAULT_CONFIGURATION_DIR , __default_db_name)
    __default_port = 5867

    def __init__(self, ip_address: str, port: int=None, db_path: str=None):
        self.ip_address = ip_address
        self.port = port or self.__default_port

        self.__db_path = db_path or self.__default_db_path    # Sqlite

    @property
    def db_path(self):
        return self.__db_path


class KMSConfig:

    class KMSConfigurationError(RuntimeError):
        pass

    __default_configuration_root = _DEFAULT_CONFIGURATION_DIR
    __default_json_config_filepath = os.path.join(__default_configuration_root, 'conf.json')

    def __init__(self,
                 keyring,
                 network_config: NetworkConfig=None,
                 policy_config: PolicyConfig=None,
                 stake_config: StakeConfig=None,
                 configuration_root: str=None,
                 json_config_filepath: str=None):

        # Check for custom paths
        self.__configuration_root = configuration_root or self.__default_configuration_root
        self.__json_config_filepath = json_config_filepath or self.__json_config_filepath

        # Subconfigurations
        self.keyring = keyring          # Everyone
        self.stake = stake_config       # Ursula
        self.policy = policy_config     # Alice / Ursula
        self.network = network_config   # Ursula

    @classmethod
    def from_json_config(cls, path: str=None):
        """TODO: Reads the config file and creates a KMSConfig instance"""
        with open(cls.__default_json_config_filepath, 'r') as config_file:
            data = json.loads(config_file.read())

    def to_json_config(self, path: str=None):
        """TODO: Serializes a configuration and saves it to the local filesystem."""
        path = path or self.__default_json_config_filepath
