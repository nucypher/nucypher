import json
import os
from pathlib import Path
from typing import Tuple, List

from web3 import Web3
from web3.contract import Contract

from nkms.blockchain.eth.sol.compile import SolidityCompiler

_DEFAULT_CONFIGURATION_DIR = os.path.join(str(Path.home()), '.nucypher')


class Registrar:
    """
    Records known contracts on the disk for future access and utility. This
    lazily writes to the filesystem during contract enrollment.

    WARNING: Unless you are developing the KMS/work at NuCypher, you most
    likely won't ever need to use this.
    """
    __DEFAULT_REGISTRAR_FILEPATH = os.path.join(_DEFAULT_CONFIGURATION_DIR, 'registrar.json')
    __DEFAULT_CHAIN_NAME = 'tester'

    class UnknownContract(KeyError):
        pass

    class UnknownChain(KeyError):
        pass

    def __init__(self, chain_name: str=None, registrar_filepath: str=None):
        self._chain_name = chain_name or self.__DEFAULT_CHAIN_NAME
        self.__registrar_filepath = registrar_filepath or self.__DEFAULT_REGISTRAR_FILEPATH

    def __write(self, registrar_data: dict) -> None:
        """
        Writes the registrar data dict as JSON to the registrar file. If no
        file exists, it will create it and write the data. If a file does exist
        and contains JSON data, it will _overwrite_ everything in it.
        """
        with open(self.__registrar_filepath, 'w+') as registrar_file:
            registrar_file.seek(0)
            registrar_file.write(json.dumps(registrar_data))
            registrar_file.truncate()

    def __read(self) -> dict:
        """
        Reads the registrar file and parses the JSON and returns a dict.
        If the file is empty or the JSON is corrupt, it will return an empty
        dict.
        If you are modifying or updating the registrar file, you _must_ call
        this function first to get the current state to append to the dict or
        modify it because _write_registrar_file overwrites the file.
        """
        try:
            with open(self.__registrar_filepath, 'r') as registrar_file:
                registrar_file.seek(0)
                registrar_data = json.loads(registrar_file.read())
                if self._chain_name not in registrar_data:
                    registrar_data[self._chain_name] = dict()
        except (json.decoder.JSONDecodeError, FileNotFoundError):
            registrar_data = {self._chain_name: dict()}
        return registrar_data

    @classmethod
    def get_registrars(cls, registrar_filepath: str=None) -> dict:
        """
        Returns a dict of Registrar objects where the key is the chain name and
        the value is the Registrar object for that chain.
        Optionally, accepts a registrar filepath.
        """
        filepath = registrar_filepath or cls.__DEFAULT_REGISTRAR_FILEPATH
        instance = cls(registrar_filepath=filepath)

        registrar_data = instance.__read()
        chain_names = registrar_data.keys()

        chains = dict()
        for chain_name in chain_names:
            chains[chain_name] = cls(chain_name=chain_name, registrar_filepath=filepath)
        return chains

    def enroll(self, contract_name: str, contract_addr: str, contract_abi: list) -> None:
        """
        Enrolls a contract to the chain registrar by writing the abi information
        to the filesystem as JSON. This can also be used to update the info
        under the specified `contract_name`.

        Note: Unless you are developing the KMS, you most likely won't ever need to use this.
        """
        contract_data = {
            contract_addr: {
                "name": contract_name,
                "abi": contract_abi,
                "addr": contract_addr
            }
        }

        registrar_data = self.__read()

        reg_contract_data = registrar_data.get(self._chain_name, dict())
        reg_contract_data.update(contract_data)

        registrar_data[self._chain_name].update(reg_contract_data)
        self.__write(registrar_data)

    def dump_chain(self) -> dict:
        """
        Returns all data from the current registrar chain as a dict.
        If no data exists for the current registrar chain, then it will raise
        KeyError.
        If you haven't specified the chain name, it's probably the tester chain.
        """

        registrar_data = self.__read()
        try:
            chain_data = registrar_data[self._chain_name]
        except KeyError:
            raise self.UnknownChain("Data does not exist for chain '{}'".format(self._chain_name))
        return chain_data

    def lookup_contract(self, contract_name: str) -> List[dict]:
        """
        Search the registarar for all contracts that match a given
        contract name and return them in a list.
        """

        chain_data = self.dump_chain()

        contracts = list()
        for _address, contract_data in chain_data.items():
            if contract_data['name'] == contract_name:
                contracts.append(contract_data)

        if len(contracts) > 0:
            return contracts
        else:
            message = "Could not identify a contract name or address with {}".format(contract_name)
            raise self.UnknownContract(message)

    def dump_contract(self, address: str=None) -> dict:
        """
        Returns contracts in a list that match the provided identifier on a
        given chain. It first attempts to use identifier as a contract name.
        If no name is found, it will attempt to use identifier as an address.
        If no contract is found, it will raise NoKnownContract.
        """

        chain_data = self.dump_chain()
        if address in chain_data:
            return chain_data[address]

        # Fallback, search by name
        for contract_identifier, contract_data in chain_data.items():
            if contract_data['name'] == address:
                return contract_data
        else:
            raise self.UnknownContract('No known contract with address {}'.format(address))


class ContractProvider:
    """
    Interacts with a solidity compiler and a registrar in order to instantiate compiled
    ethereum contracts with the given web3 provider backend.
    """

    def __init__(self, provider_backend: Web3,
                 registrar: Registrar,
                 deployer_address: str=None,
                 sol_compiler: SolidityCompiler=None):

        self.w3 = provider_backend

        # TODO: Move to deployers?
        if deployer_address is None:
            deployer_address = self.w3.eth.coinbase  # coinbase / etherbase
        self.deployer_address = deployer_address

        # if a SolidityCompiler class instance was passed, compile from sources
        if sol_compiler is not None:
            recompile = True
        else:
            recompile = False
        self.__recompile = recompile
        self.__sol_compiler = sol_compiler

        if self.__recompile is True:
            interfaces = self.__sol_compiler.compile()
        else:
            interfaces = self.__registrar.dump_chain()

        # Setup the registrar and base contract factory cahche
        self.__registrar = registrar
        self.__raw_contract_cache = interfaces

    class ProviderError(Exception):
        pass

    def get_contract_factory(self, contract_name):
        """Retrieve compiled interface data from the cache and return web3 contract"""
        try:
            interface = self.__raw_contract_cache[contract_name]
        except KeyError:
            raise self.ProviderError('{} is not a compiled contract.'.format(contract_name))

        contract = self.w3.eth.contract(abi=interface['abi'],
                                        bytecode=interface['bin'],
                                        ContractFactoryClass=Contract)

        return contract

    def get_contract_address(self, contract_name: str) -> List[str]:
        """Retrieve all known addresses for this contract"""
        contracts = self.__registrar.lookup_contract(contract_name=contract_name)
        addresses = [c['addr'] for c in contracts]
        return addresses

    def deploy_contract(self, contract_name: str, *args, **kwargs) -> Tuple[Contract, str]:
        """
        Retrieve compiled interface data from the cache and
        return an instantiated deployed contract
        """

        #
        # Build the deployment tx #
        #
        contract_factory = self.get_contract_factory(contract_name=contract_name)
        deploy_transaction = {'from': self.deployer_address, 'gasPrice': self.w3.eth.gasPrice}
        deploy_bytecode = contract_factory.constructor(*args, **kwargs).buildTransaction(deploy_transaction)

        # TODO: Logging
        contract_sizes = dict()
        if len(deploy_bytecode['data']) > 1000:
            contract_sizes[contract_name] = str(len(deploy_bytecode['data']))

        #
        # Transmit the deployment tx #
        #
        txhash = contract_factory.constructor(*args, **kwargs).transact(transaction=deploy_transaction)

        # Wait for receipt
        receipt = self.w3.eth.waitForTransactionReceipt(txhash)
        address = receipt['contractAddress']

        #
        # Instantiate & enroll contract
        #
        contract = contract_factory(address=address)
        self.__registrar.enroll(contract_name=contract_name,
                                contract_addr=contract.address,
                                contract_abi=contract_factory.abi)

        return contract, txhash

    def get_contract(self, address: str) -> Contract:
        """Instantiate a deployed contract from registrar data"""
        contract_data = self.__registrar.dump_contract(address=address)
        contract = self.w3.eth.contract(abi=contract_data['abi'], address=contract_data['addr'])
        return contract
