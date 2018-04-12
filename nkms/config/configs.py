import json
import os
from pathlib import Path

import maya

_DEFAULT_CONFIGURATION_DIR = os.path.join(str(Path.home()), '.nucypher')


class KMSConfigurationError(RuntimeError):
    pass


class KMSProvider:

    def __init__(self, provider=None, registrar=None):

        if provider is None:
            # https: // github.com / ethereum / eth - tester     # available-backends
            eth_tester = EthereumTester(backend=PyEVMBackend())  # TODO: Discuss backend choice
            provider = EthereumTesterProvider(ethereum_tester=eth_tester, api_endpoints=None)
        self.provider = provider
        self.w3 = Web3(self.provider)

        self.__registrar = None

    def __make_web3_contracts(self, contract_factory: Union[ConciseContract, Contract]=ConciseContract, address=None) -> List[Contract]:
        """Instantiate web3 Contracts from raw contract interface data with the supplied web3 provider"""
        sol_config = SolidityConfig()
        interfaces = compile_interfaces(config=sol_config)

        if contract_factory is ConciseContract and address is None:
            raise Exception('Address must be provided when making concise contracts.')
        elif contract_factory is Contract and address is not None:
            raise Exception('Address must not be provided when making deployable, non-concise contracts')

        web3_contracts = list()
        for contract, interface in interfaces.items():
            contract = self.w3.eth.contract(abi=interface['abi'],
                                            bytecode=interface['bin'],
                                            ContractFactoryClass=contract_factory)
            web3_contracts.append(contract)

        return web3_contracts

    def get_contract(self):
        pass

    def deploy_contract(self):
        pass


class StakeConfig:
    # __minimum_stake_amount = 0  # TODO
    # __minimum_stake_duration = 0

    def __init__(self, amount: int, periods: int, start_datetime):

        assert StakeConfig.validate_stake(amount, periods, start_datetime)
        self.amount = amount
        self.start = start_datetime
        self.periods = periods

    @classmethod
    def validate_stake(cls, amount: int, periods: int, start_datetime) -> bool:
        rules = (
            # (amount > cls.__minimum_stake_amount, 'Staking aount must be at least {min_amount}'),  # TODO
            (start_datetime < maya.now(), 'Start date/time must not be in the past.'),
            # (periods > cls.__minimum_stake_duration, 'Staking duration must be at least {}'.format(cls.__minimum_stake_duration))
        )

        for rule, failure_message in rules:
            if rule is False:
                raise KMSConfigurationError(failure_message)
        else:
            return True


class PolicyConfig:
    __default_m = 6  # TODO!!!
    __default_n = 10
    __default_gas_limit = 500000

    def __init__(self, default_m: int, default_n: int, gas_limit: int):
        self.prefered_m = default_m or self.__default_m
        self.prefered_n = default_n or self.__default_n
        self.transaction_gas_limit = gas_limit or self.__default_gas_limit


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
