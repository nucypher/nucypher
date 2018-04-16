import json
import os
from pathlib import Path
from typing import Tuple

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

    def dump_contract(self, identifier: str=None) -> dict:
        """
        Returns contracts in a list that match the provided identifier on a
        given chain. It first attempts to use identifier as a contract name.
        If no name is found, it will attempt to use identifier as an address.
        If no contract is found, it will raise NoKnownContract.
        """
        chain_data = self.dump_chain()
        if identifier in chain_data:
            contract_data = chain_data[identifier]
            return contract_data
        else:
            for contract_name, contract_data in chain_data.items():
                if contract_data['name'] == identifier:
                    return contract_data

        error_message = "Could not identify a contract name or address with {}".format(identifier)
        raise self.UnknownContract(error_message)


class ContractProvider:
    """
    Interacts with a solidity compiler and a registrar in order to instantiate compiled
    ethereum contracts with the given web3 provider backend.
    """

    def __init__(self, provider_backend,
                 registrar: Registrar,
                 deployer_address:str =None,
                 sol_compiler: SolidityCompiler=None):

        self.__provider_backend = provider_backend
        self.w3 = Web3(self.__provider_backend)

        if deployer_address is None:
            deployer_address = self.w3.eth.coinbase
        self.deployer_address = deployer_address

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

        self.__registrar = registrar
        self.__raw_contract_cache = interfaces

    class ProviderError(Exception):
        pass

    def get_contract(self, contract_name: str=None) -> Contract:
        contract_data = self.__registrar.dump_contract(contract_name)
        contract = self.w3.eth.contract(abi=contract_data['abi'], address=contract_data['addr'])
        return contract

    def deploy_contract(self, contract_name: str, *args, **kwargs) -> Tuple[Contract, str]:
        try:
            interface = self.__raw_contract_cache[contract_name]
        except KeyError:
            raise self.ProviderError('{} is not a compiled contract.'.format(contract_name))

        contract = self.w3.eth.contract(abi=interface['abi'],
                                        bytecode=interface['bin'],
                                        ContractFactoryClass=Contract)

        deploy_transaction = {'from': self.deployer_address}
        deploy_bytecode = contract.constructor(*args, **kwargs).buildTransaction(deploy_transaction)

        txhash = self.w3.eth.sendTransaction(deploy_bytecode)  # deploy!
        receipt = self.w3.eth.waitForTransactionReceipt(txhash)

        address = receipt['contractAddress']
        contract = contract(address=address)

        # Commit to registrar
        self.__registrar.enroll(contract_name=contract_name,
                                contract_addr=address,
                                contract_abi=interface['abi'])

        return contract, txhash

    def get_or_deploy_contract(self, contract_name: str, *args, **kwargs) -> Tuple[Contract, str]:
        try:
            contract = self.get_contract(contract_name=contract_name)
            txhash = None
        except (Registrar.UnknownContract, Registrar.UnknownChain):
            contract, txhash = self.deploy_contract(contract_name, *args, **kwargs)

        return contract, txhash
