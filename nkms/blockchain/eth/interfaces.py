import json
import os
from pathlib import Path
from typing import Tuple, ClassVar, Dict, Union

from eth_tester import EthereumTester, PyEVMBackend
from web3 import Web3, EthereumTesterProvider
from web3.contract import ConciseContract, Contract

from nkms.blockchain.eth.sol.compile import compile_interfaces, SolidityConfig


_DEFAULT_CONFIGURATION_DIR = os.path.join(str(Path.home()), '.nucypher')


def _write_registrar_file(registrar_data: dict, registrar_filepath: str) -> None:
    """
    Writes the registrar data dict as JSON to the registrar file. If no
    file exists, it will create it and write the data. If a file does exist
    and contains JSON data, it will _overwrite_ everything in it.
    """
    with open(registrar_filepath, 'w+') as registrar_file:
        registrar_file.seek(0)
        registrar_file.write(json.dumps(registrar_data))
        registrar_file.truncate()


def _read_registrar_file(registrar_filepath: str) -> dict:
    """
    Reads the registrar file and parses the JSON and returns a dict.
    If the file is empty or the JSON is corrupt, it will return an empty
    dict.
    If you are modifying or updating the registrar file, you _must_ call
    this function first to get the current state to append to the dict or
    modify it because _write_registrar_file overwrites the file.
    """
    try:
        with open(registrar_filepath, 'r') as registrar_file:
            registrar_file.seek(0)
            registrar_data = json.loads(registrar_file.read())
    except (json.decoder.JSONDecodeError, FileNotFoundError):
        registrar_data = dict()

    return registrar_data


class Registrar:
    """
    Records known contracts on the disk for future access and utility.

    WARNING: Unless you are developing the KMS/work at NuCypher, you most
    likely won't ever need to use this.
    """
    __DEFAULT_REGISTRAR_FILEPATH = os.path.join(_DEFAULT_CONFIGURATION_DIR, 'registrar.json')
    __DEFAULT_CHAIN_NAME = 'tester'

    class NoKnownContract(KeyError):
        pass

    def __init__(self, chain_name: str=None, registrar_filepath: str=None):
        self._chain_name = chain_name or self.__DEFAULT_CHAIN_NAME
        self.__registrar_filepath = registrar_filepath or self.__DEFAULT_REGISTRAR_FILEPATH

    @classmethod
    def get_chains(cls, registrar_filepath: str=None) -> dict:
        """
        Returns a dict of Registrar objects where the key is the chain name and
        the value is the Registrar object for that chain.
        Optionally, accepts a registrar filepath.
        """
        filepath = registrar_filepath or cls.__DEFAULT_REGISTRAR_FILEPATH
        instance = cls(registrar_filepath=filepath)

        registrar_data = _read_registrar_file(filepath)
        chain_names = registrar_data.keys()

        chains = dict()
        for chain_name in chain_names:
            chains[chain_name] = cls(chain_name=chain_name,
                                     registrar_filepath=filepath)
        return chains

    def enroll(self, contract_name: str, contract_address: str, contract_abi: list) -> None:
        """
        Enrolls a contract to the chain registrar by writing the abi information
        to the filesystem as JSON. This can also be used to update the info
        under the specified `contract_name`.

        WARNING: Unless you are developing the KMS/work at NuCypher, you most
        likely won't ever need to use this.
        """
        enrolled_contract = {
                self._chain_name: {
                    contract_name: {
                        "addr": contract_address,
                        "abi": contract_abi
                }
            }
        }

        registrar_data = _read_registrar_file(self.__registrar_filepath)
        registrar_data.update(enrolled_contract)

        _write_registrar_file(registrar_data, self.__registrar_filepath)

    def get_chain_data(self) -> dict:
        """
        Returns all data from the current registrar chain as a dict.
        If no data exists for the current registrar chain, then it will raise
        KeyError.
        If you haven't specified the chain name, it's probably the tester chain.
        """
        registrar_data = _read_registrar_file(self.__registrar_filepath)
        try:
            chain_data = registrar_data[self._chain_name]
        except KeyError:
            raise KeyError("Data does not exist for chain '{}'".format(self._chain_name))
        return chain_data

    def get_contract_data(self, identifier: str=None) -> dict:
        """
        Returns contract data on the chain as a dict given an `identifier`.
        It first attempts to use identifier as a contract name. If no name is
        found, it will attempt to use identifier as an address.
        If no contract is found, it will raise NoKnownContract.
        """
        chain_data = self.get_chain_data()
        if identifier in chain_data:
            contract_data = chain_data[identifier]
            return contract_data
        else:
            for contract_name, contract_data in chain_data.items():
                if contract_data['addr'] == identifier:
                    return contract_data
        raise self.NoKnownContract(
            "Could not identify a contract name or address with {}".format(identifier)
        )


class Provider:
    """
    Interacts with a registrar in order to interface with compiled
    ethereum contracts with the given provider backend.
    """

    def __init__(self, provider_backend=None, registrar: Registrar=None):

        # Provider backend
        if provider_backend is None:
            # https: // github.com / ethereum / eth - tester     # available-backends
            eth_tester = EthereumTester(backend=PyEVMBackend())  # TODO: Discuss backend choice
            provider_backend = EthereumTesterProvider(ethereum_tester=eth_tester) # , api_endpoints=None)
        self.provider = provider_backend
        self.web3 = Web3(self.provider)

        if registrar is None:
            registrar = Registrar(chain_name='tester')  # TODO: move to config

        self.__registrar = registrar

        self.__contract_cache = None  # set on the next line
        self.cache_contracts(compile=True)

    class ProviderError(Exception):
        pass

    class UnknownContract(KeyError):
        pass

    @staticmethod
    def __compile(config: SolidityConfig=None) -> Dict[str, Contract]:
        sol_config = config or SolidityConfig()
        interfaces = compile_interfaces(config=sol_config)
        return interfaces

    def __make_web3_contracts(self, interfaces, contract_factory=Union[Contract, ConciseContract]):
        """Instantiate web3 Contracts from raw contract interface data with the supplied web3 provider"""

        web3_contracts = dict()
        for contract_name, interface in interfaces.items():
            bytecode = None if contract_factory is ConciseContract else interface['bin']

            contract = self.web3.eth.contract(abi=interface['abi'],
                                                   bytecode=bytecode,  # Optional, needed for deployment
                                                   ContractFactoryClass=Contract)

            web3_contracts[contract_name] = contract

        return web3_contracts

    def cache_contracts(self, compile: bool=False) -> None:
        """Loads from contract interface data registrar or compiles"""
        if compile is False:
            interface_records = self.__registrar.get_chain_data()
            contract_factory = ConciseContract
            contracts = self.__make_web3_contracts(interface_records, contract_factory)
        else:
            interfaces = self.__compile()
            contract_factory = Contract
            contracts = self.__make_web3_contracts(interfaces, contract_factory)
        self.__contract_cache = contracts

    def __get_cached_contract(self, contract_name):
        try:
            contract = self.__contract_cache[contract_name]
        except KeyError:
            raise self.UnknownContract('{} is not a compiled contract.'.format(contract_name))
        else:
            return contract

    def deploy_contract(self, contract_name: str, *args, **kwargs) -> Tuple[str, str]:
        contract = self.__get_cached_contract(contract_name)

        transaction = {'from': self.web3.eth.coinbase}

        deploy_bytecode = contract.constructor(*args, **kwargs).buildTransaction(transaction)

        txhash = self.web3.eth.sendTransaction(deploy_bytecode)  # deploy!
        receipt = self.web3.eth.waitForTransactionReceipt(txhash)
        # receipt = self.web3.eth.getTransactionReceipt(txhash)
        address = receipt['contractAddress']

        try:
            cached_contract = self.__contract_cache[contract_name]
            contract = contract(address=address)
        except KeyError:
            raise  # TODO
        else:
            self.__registrar.enroll(contract_name=contract_name,
                                    contract_address=address,
                                    contract_abi=cached_contract.abi)

        return contract, txhash

    def get_contract(self, contract_name: str=None):
        contract_data = self.__registrar.get_contract_data(contract_name)
        contract = self.web3.eth.contract(abi=contract_data['abi'], address=contract_data['addr'])
        return contract

    def get_or_deploy_contract(self, contract_name, *args, **kwargs):
        try:
            contract = self.get_contract(contract_name=contract_name)
            txhash = None
        except (KeyError, Registrar.NoKnownContract):
            contract, txhash = self.deploy_contract(contract_name, *args, **kwargs)

        return contract, txhash
