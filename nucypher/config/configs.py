import json
import os
import warnings
from pathlib import Path
from typing import List

from web3 import IPCProvider

from nucypher.blockchain.eth.chains import Blockchain, TesterBlockchain


class NucypherConfiguration:

    _default_configuration_directory = os.path.join(str(Path.home()), '.nucypher')
    _identifier = NotImplemented  # used as json config key

    class NucypherConfigurationError(RuntimeError):
        pass

    def __init__(self, base_directory: str=None):
        self.base_directory = base_directory or self._default_configuration_directory

    def _save(self, path: str=None):
        raise NotImplementedError

    @classmethod
    def _load(cls, path: str=None):
        """Instantiate a configuration object by reading from saved json file data"""

        with open(path or cls._default_configuration_directory, 'r') as config:
            data_dump = json.loads(config.read())
        try:
            subconfiguration_data = data_dump[cls._identifier]
        except KeyError:
            raise cls.NucypherConfigurationError('No saved configuration for {}'.format(cls._identifier))

        try:
            instance = cls(**subconfiguration_data)
        except ValueError:  # TODO: Correct exception?
            raise cls.NucypherConfigurationError("Invalid configuration file data: {}.".format(subconfiguration_data))

        return instance


class PolicyConfiguration(NucypherConfiguration):
    """Preferences regarding the authoring of new Policies, as Alice"""
    _identifier = 'policy'

    __default_m = 6  # TODO: Determine sensible values through experience
    __default_n = 10

    def __init__(self, default_m: int, default_n: int, *args, **kwargs):
        self.prefered_m = default_m or self.__default_m
        self.prefered_n = default_n or self.__default_n
        super().__init__(*args, **kwargs)


class NetworkConfiguration(NucypherConfiguration):
    """Network configuration class for all things network transport"""
    _identifier = 'network'

    # Database
    __default_db_name = 'nucypher_datastore.db'  # TODO: choose database filename
    __default_db_path = os.path.join(NucypherConfiguration._default_configuration_directory, __default_db_name)

    # DHT Server
    __default_dht_port = 5867

    # REST Server
    __default_ip_address = '127.0.0.1'
    __default_rest_port = 5115  # TODO: choose a default rest port

    def __init__(self, ip_address: str=None, rest_port: int=None,
                 dht_port: int=None, db_name: str=None, *args, **kwargs):
        # Database
        self.db_name = db_name or self.__default_db_name
        # self.__db_path = db_path or self.__default_db_path    # Sqlite

        # DHT Server
        self.dht_port = dht_port or self.__default_dht_port

        # Rest Server
        self.ip_address = ip_address or self.__default_ip_address
        self.rest_port = rest_port or self.__default_rest_port

        super().__init__(*args, **kwargs)


class BlockchainConfiguration(NucypherConfiguration):
    """
    Blockchain configuration class, takes and preserves
    the state of Web3 (and thus the blockchain) provider objects during runtime.

    Network Name
    ==============
    Network names are used primarily for the ethereum contract registry,
    but also are sometimes used in determining the network configuration.

    Geth networks
    -------------
    mainnet: Connect to the public ethereum mainnet via geth.
    ropsten: Connect to the public ethereum ropsten testnet via geth.
    temp: Local private chain whos data directory is removed when the chain is shutdown. Runs via geth.


    Development Chains
    ------------------
    tester: Ephemeral in-memory chain backed by pyethereum, pyevm, etc.
    testrpc: Ephemeral in-memory chain for testing RPC calls

    """
    _identifier = 'blockchain'

    # Blockchain Network
    __default_network = 'tester'
    __default_timeout = 120  # seconds
    __default_transaction_gas_limit = 500000  # TODO: determine sensible limit

    def __init__(self, wallet_address: str=None, network: str=None, timeout: int=None,
                 transaction_gas_limit=None, compiler=None, registrar=None,
                 deploy=False, tester=False, *args, **kwargs):

        self.__network = network if network is not None else self.__default_network
        self.timeout = timeout if timeout is not None else self.__default_timeout
        self.transaction_gas_limit = transaction_gas_limit or self.__default_transaction_gas_limit
        self.__user_wallet_addresses = list()

        if wallet_address is not None:
            self.__user_wallet_addresses.append(wallet_address)

        super().__init__(*args, **kwargs)

    #
    # Wallets
    #
    @property
    def wallet_addresses(self) -> List[str]:
        return self.__user_wallet_addresses

    def add_wallet_address(self, ether_address: str) -> None:
        """TODO: Validate"""
        if len(ether_address) != 42:  # includes 0x prefix
            raise ValueError("Invalid ethereum address: {}".format(ether_address))
        self.__user_wallet_addresses.append(ether_address)


class CharacterConfiguration(NucypherConfiguration):
    """Encapsulates all sub-configurations, preserves the configurable state of a single character."""

    _identifier = 'character'

    __default_configuration_root = NucypherConfiguration._default_configuration_directory
    __default_json_config_filepath = os.path.join(__default_configuration_root, 'conf.json')

    def __init__(self,
                 keyring=None,
                 blockchain_config: BlockchainConfiguration=None,
                 network_config: NetworkConfiguration=None,
                 policy_config: PolicyConfiguration=None,
                 configuration_root: str=None,
                 json_config_filepath: str=None,
                 *args, **kwargs):

        # Check for custom paths
        self.__configuration_root = configuration_root or self.__default_configuration_root
        self.__json_config_filepath = json_config_filepath or self.__default_json_config_filepath

        if blockchain_config is None:
            blockchain_config = BlockchainConfiguration()

        # Sub-configurations                                     # Who needs it...
        self.keyring = keyring                                   # Everyone
        self.blockchain = blockchain_config                      # Everyone
        self.policy = policy_config                              # Alice / Ursula
        self.network = network_config or NetworkConfiguration()  # Ursula

        super().__init__(*args, **kwargs)
