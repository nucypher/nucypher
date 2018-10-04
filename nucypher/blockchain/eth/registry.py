import json
import os
import tempfile
from json import JSONDecodeError
from logging import getLogger

import shutil
from constant_sorrow import constants
from typing import Union

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

    class EmptyRegistry(RegistryError):
        pass

    class NoRegistry(RegistryError):
        pass

    class UnknownContract(RegistryError):
        pass

    class IllegalRegistry(RegistryError):
        """Raised when invalid data is encountered in the registry"""

    def __init__(self, registry_filepath: str = __default_registry_path) -> None:
        self.log = getLogger("registry")
        self.__filepath = registry_filepath

    @property
    def filepath(self):
        return self.__filepath

    def _swap_registry(self, filepath: str) -> bool:
        self.__filepath = filepath
        return True

    def __write(self, registry_data: list) -> None:
        """
        Writes the registry data list as JSON to the registry file. If no
        file exists, it will create it and write the data. If a file does exist
        it will _overwrite_ everything in it.
        """
        with open(self.__filepath, 'w+') as registry_file:
            registry_file.seek(0)
            registry_file.write(json.dumps(registry_data))
            registry_file.truncate()

    def read(self) -> list:
        """
        Reads the registry file and parses the JSON and returns a list.
        If the file is empty it will return an empty list.
        If you are modifying or updating the registry file, you _must_ call
        this function first to get the current state to append to the dict or
        modify it because _write_registry_file overwrites the file.
        """

        try:
            with open(self.__filepath, 'r') as registry_file:
                self.log.debug("Reading from registrar: filepath {}".format(self.__filepath))
                registry_file.seek(0)
                file_data = registry_file.read()
                if file_data:
                    registry_data = json.loads(file_data)
                else:
                    registry_data = list()

        except FileNotFoundError:
            raise self.NoRegistry("No registry at filepath: {}".format(self.__filepath))

        except JSONDecodeError:
            raise

        return registry_data

    def enroll(self, contract_name, contract_address, contract_abi):
        """
        Enrolls a contract to the chain registry by writing the name, address,
        and abi information to the filesystem as JSON.

        Note: Unless you are developing NuCypher, you most likely won't ever
        need to use this.
        """
        contract_data = [contract_name, contract_address, contract_abi]
        try:
            registry_data = self.read()
        except self.RegistryError:
            self.log.info("Blank registry encountered: enrolling {}:{}".format(contract_name, contract_address))
            registry_data = list()  # empty registry

        registry_data.append(contract_data)
        self.__write(registry_data)
        self.log.info("Enrolled {}:{} into registry {}".format(contract_name, contract_address, self.filepath))

    def search(self, contract_name: str=None, contract_address: str=None):
        """
        Searches the registry for a contract with the provided name or address
        and returns the contracts.
        """
        if not (bool(contract_name) ^ bool(contract_address)):
            raise ValueError("Pass contract_name or contract_address, not both.")

        contracts = list()
        registry_data = self.read()

        try:
            for name, addr, abi in registry_data:
                if contract_name == name or contract_address == addr:
                    contracts.append((name, addr, abi))
        except ValueError:
            message = "Missing or corrupted registry data".format(self.__filepath)
            self.log.critical(message)
            raise self.IllegalRegistry(message)

        if not contracts:
            raise self.UnknownContract

        if contract_address and len(contracts) > 1:
            m = "Multiple records returned for address {}"
            self.log.critical(m)
            raise self.IllegalRegistry(m.format(contract_address))

        return contracts if contract_name else contracts[0]


class TemporaryEthereumContractRegistry(EthereumContractRegistry):

    def __init__(self) -> None:
        _, self.temp_filepath = tempfile.mkstemp()
        super().__init__(registry_filepath=self.temp_filepath)

    def clear(self):
        self.log.info("Cleared temporary registry at {}".format(self.filepath))
        with open(self.filepath, 'w') as registry_file:
            registry_file.write('')

    def cleanup(self):
        os.remove(self.temp_filepath)  # remove registrar tempfile

    def commit(self, filepath) -> str:
        """writes the current state of the registry to a file"""
        self.log.info("Committing temporary registry to {}".format(filepath))
        self._swap_registry(filepath)                     # I'll allow it

        if os.path.exists(filepath):
            self.log.debug("Removing registry {}".format(filepath))
            self.clear()                                  # clear prior sim runs

        _ = shutil.copy(self.temp_filepath, filepath)
        self.temp_filepath = constants.REGISTRY_COMMITED  # just in case
        self.log.info("Wrote temporary registry to filesystem {}".format(filepath))
        return filepath
