import json
import os
import warnings
from pathlib import Path

from web3 import IPCProvider
from web3.middleware import geth_poa_middleware

from nucypher.blockchain.eth.chains import Blockchain, TesterBlockchain
from nucypher.blockchain.eth.sol.compile import SolidityCompiler

_DEFAULT_CONFIGURATION_DIR = os.path.join(str(Path.home()), '.nucypher')


class NucypherConfigurationError(RuntimeError):
    pass


class PolicyConfig:
    __default_m = 6  # TODO!!!
    __default_n = 10
    __default_gas_limit = 500000

    def __init__(self, default_m: int, default_n: int, gas_limit: int):
        self.prefered_m = default_m or self.__default_m
        self.prefered_n = default_n or self.__default_n
        self.transaction_gas_limit = gas_limit or self.__default_gas_limit


class NetworkConfig:
    __default_db_name = 'nucypher_datastore.db'  # TODO
    __default_db_path = os.path.join(_DEFAULT_CONFIGURATION_DIR , __default_db_name)
    __default_port = 5867

    def __init__(self, ip_address: str, port: int=None, db_path: str=None):
        self.ip_address = ip_address
        self.port = port or self.__default_port

        self.__db_path = db_path or self.__default_db_path    # Sqlite

    @property
    def db_path(self):
        return self.__db_path


class BlockchainConfig:
    """

    Holds in

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

    __default_providers = (IPCProvider(ipc_path='/tmp/geth.ipc'),
                           # user-managed geth over IPC assumed
                           )

    __default_network = 'tester'
    __default_timeout = 120          # seconds
    __configured_providers = list()  # tracks active providers

    def __init__(self, network: str=None, timeout: int=None,
                 compiler=None, registrar=None, deploy=False,
                 geth=True, tester=False):

        # Parse configuration

        if len(self.__configured_providers) == 0:
            warnings.warn("No blockchain provider backends are configured, using default.", RuntimeWarning)
            self.__providers = BlockchainConfig.__default_providers

        self._providers = self.__configured_providers
        self.__network = network if network is not None else self.__default_network
        self.__timeout = timeout if timeout is not None else self.__default_timeout

        if deploy is False:
            from nucypher.blockchain.eth.interfaces import ContractInterface
            interface_class = ContractInterface
        else:
            from nucypher.blockchain.eth.interfaces import DeployerInterface
            interface_class = DeployerInterface

        interface = interface_class(blockchain_config=self, sol_compiler=compiler, registrar=registrar)

        if tester is True:
            blockchain_class = TesterBlockchain
        else:
            blockchain_class = Blockchain

        # Initial connection to blockchain via provider
        self.chain = blockchain_class(interface=interface)

    @classmethod
    def add_provider(cls, provider):
        cls.__configured_providers.append(provider)

    @property
    def providers(self) -> list:
        return self._providers

    @property
    def network(self):
        return self.__network

    @property
    def timeout(self):
        return self.__timeout


class NucypherConfig:

    __instance = None
    __default_configuration_root = _DEFAULT_CONFIGURATION_DIR
    __default_json_config_filepath = os.path.join(__default_configuration_root, 'conf.json')

    def __init__(self,
                 keyring=None,
                 blockchain_config: BlockchainConfig=None,
                 network_config: NetworkConfig=None,
                 policy_config: PolicyConfig=None,
                 configuration_root: str=None,
                 json_config_filepath: str=None):

        # Check for custom paths
        self.__configuration_root = configuration_root or self.__default_configuration_root
        self.__json_config_filepath = json_config_filepath or self.__default_json_config_filepath

        if blockchain_config is None:
            blockchain_config = BlockchainConfig()

        # Sub-configurations
        self.keyring = keyring               # Everyone
        self.blockchain = blockchain_config  # Everyone
        self.policy = policy_config          # Alice / Ursula
        self.network = network_config        # Ursula

        if self.__instance is not None:
            raise RuntimeError('Configuration not started')
        else:
            self.__instance = self

    @classmethod
    def get(cls):
        return cls.__instance

    @classmethod
    def reset(cls) -> None:
        cls.__instance = None

    def __read(cls, path: str=None):
        """TODO: Reads the config file and creates a NuCypherConfig instance"""
        with open(cls.__default_json_config_filepath, 'r') as config_file:
            data = json.loads(config_file.read())

    def __write(self, path: str=None):
        """TODO: Serializes a configuration and saves it to the local filesystem."""
        path = path or self.__default_json_config_filepath
