import json
import os
from typing import Union

import shutil
import tempfile

from constant_sorrow import constants

from nucypher.config.constants import DEFAULT_CONFIG_ROOT


class EthereumContractRegistry:
    """
    Records known contracts on the disk for future access and utility. This
    lazily writes to the filesystem during contract enrollment.

    WARNING: Unless you are developing NuCypher, you most likely won't ever need
    to use this.
    """
    # TODO: Integrate with config classes
    __default_registry_path = os.path.join(DEFAULT_CONFIG_ROOT, 'contract_registry.json')

    class RegistryError(Exception):
        pass

    class UnknownContract(RegistryError):
        pass

    class IllegalRegistrar(RegistryError):
        """Raised when invalid data is encountered in the registry"""

    def __init__(self, registry_filepath: str=None) -> None:
        self.__registry_filepath = registry_filepath or self.__default_registry_path

    @classmethod
    def from_config(cls, config) -> Union['EthereumContractRegistry', 'TemporaryEthereumContractRegistry']:
        if config.temp_registry is True:                # In memory only
            return TemporaryEthereumContractRegistry()
        else:
            return EthereumContractRegistry()

    @property
    def registry_filepath(self):
        return self.__registry_filepath

    def _swap_registry(self, filepath: str) -> bool:
        self.__registry_filepath = filepath
        return True

    def __write(self, registry_data: list) -> None:
        """
        Writes the registry data list as JSON to the registry file. If no
        file exists, it will create it and write the data. If a file does exist
        it will _overwrite_ everything in it.
        """
        with open(self.__registry_filepath, 'w+') as registry_file:
            registry_file.seek(0)
            registry_file.write(json.dumps(registry_data))
            registry_file.truncate()

    def read(self) -> list:
        """
        Reads the registry file and parses the JSON and returns a list.
        If the file is empty or the JSON is corrupt, it will return an empty
        list.
        If you are modifying or updating the registry file, you _must_ call
        this function first to get the current state to append to the dict or
        modify it because _write_registry_file overwrites the file.
        """
        try:
            with open(self.__registry_filepath, 'r') as registry_file:
                registry_file.seek(0)
                file_data = registry_file.read()
                if file_data:
                    registry_data = json.loads(file_data)
                else:
                    registry_data = list()  # Existing, but empty registry

        except FileNotFoundError:
            raise self.RegistryError("No registy at filepath: {}".format(self.__registry_filepath))

        return registry_data

    def enroll(self, contract_name, contract_address, contract_abi):
        """
        Enrolls a contract to the chain registry by writing the name, address,
        and abi information to the filesystem as JSON.

        Note: Unless you are developing NuCypher, you most likely won't ever
        need to use this.
        """
        contract_data = [contract_name, contract_address, contract_abi]
        registry_data = self.read()
        registry_data.append(contract_data)
        self.__write(registry_data)

    def search(self, contract_name: str=None, contract_address: str=None):
        """
        Searches the registry for a contract with the provided name or address
        and returns the contracts.
        """
        if not (bool(contract_name) ^ bool(contract_address)):
            raise ValueError("Pass contract_name or contract_address, not both.")

        contracts = list()
        registry_data = self.read()

        for name, addr, abi in registry_data:
            if contract_name == name or contract_address == addr:
                contracts.append((name, addr, abi))

        if not contracts:
            raise self.UnknownContract
        if contract_address and len(contracts) > 1:
            m = "Multiple records returned for address {}"
            raise self.IllegalRegistrar(m.format(contract_address))

        return contracts if contract_name else contracts[0]


class TemporaryEthereumContractRegistry(EthereumContractRegistry):

    def __init__(self) -> None:
        _, self.temp_filepath = tempfile.mkstemp()
        super().__init__(registry_filepath=self.temp_filepath)

    def clear(self):
        with open(self.registry_filepath, 'w') as registry_file:
            registry_file.write('')

    def reset(self):
        os.remove(self.temp_filepath)  # remove registrar tempfile

    def commit(self, filepath) -> str:
        """writes the current state of the registry to a file"""
        self._swap_registry(filepath)                     # I'll allow it

        if os.path.exists(filepath):
            self.clear()                                  # clear prior sim runs

        _ = shutil.copy(self.temp_filepath, filepath)
        self.temp_filepath = constants.REGISTRY_COMMITED  # just in case
        return filepath
