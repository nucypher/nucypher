"""
This file is part of nucypher.

nucypher is free software: you can redistribute it and/or modify
it under the terms of the GNU Affero General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

nucypher is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU Affero General Public License for more details.

You should have received a copy of the GNU Affero General Public License
along with nucypher.  If not, see <https://www.gnu.org/licenses/>.
"""
import base64
import json
import os
import pprint
import tempfile
from json import JSONDecodeError
from os.path import dirname, abspath

import requests
from twisted.logger import Logger

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

    _multi_contract = True
    _contract_name = NotImplemented

    _default_registry_filepath = os.path.join(DEFAULT_CONFIG_ROOT, 'contract_registry.json')

    __PUBLICATION_USER = "nucypher"
    __PUBLICATION_REPO = f"{__PUBLICATION_USER}/ethereum-contract-registry"

    # Registry
    REGISTRY_NAME = 'contract_registry.json'

    class RegistryError(Exception):
        pass

    class RegistrySourceUnavailable(RegistryError):
        pass

    class EmptyRegistry(RegistryError):
        pass

    class NoRegistry(RegistryError):
        pass

    class UnknownContract(RegistryError):
        pass

    class IllegalRegistry(RegistryError):
        """Raised when invalid data is encountered in the registry"""

    def __init__(self, registry_filepath: str = None) -> None:
        self.log = Logger("registry")
        self.__filepath = registry_filepath or self._default_registry_filepath

    @classmethod
    def _get_registry_class(cls, local=False):
        """
        If "local" is True, it means we are running a local blockchain and we
        have deployed the Nucypher contracts on that blockchain, therefore
        we do not want to download a registry from github.
        """
        return LocalEthereumContractRegistry if local else cls

    @classmethod
    def download_latest_publication(cls, filepath: str = None, branch: str = 'goerli') -> str:
        """
        Get the latest published contract registry from github and save it on the local file system.
        """

        # Setup
        github_endpoint = f'https://raw.githubusercontent.com/{cls.__PUBLICATION_REPO}/{branch}/{cls.REGISTRY_NAME}'
        response = requests.get(github_endpoint)

        # Fetch
        if response.status_code != 200:
            error = f"Failed to fetch registry from {github_endpoint} with status code {response.status_code}"
            raise cls.RegistrySourceUnavailable(error)

        # Get filename
        # TODO : Use envvar for config root and registry path
        filepath = filepath or cls._default_registry_filepath

        # Ensure parent path exists
        os.makedirs(abspath(dirname(filepath)), exist_ok=True)

        # Write registry
        with open(filepath, 'wb') as registry_file:
            registry_file.write(response.content)

        return filepath

    @classmethod
    def from_latest_publication(cls, filepath: str = None, branch: str = 'goerli') -> 'EthereumContractRegistry':
        filepath = cls.download_latest_publication(filepath=filepath, branch=branch)
        instance = cls(registry_filepath=filepath)
        return instance

    @property
    def filepath(self):
        return self.__filepath

    @property
    def enrolled_names(self):
        entries = iter(record[0] for record in self.read())
        return entries

    @property
    def enrolled_addresses(self):
        entries = iter(record[1] for record in self.read())
        return entries

    def _swap_registry(self, filepath: str) -> bool:
        self.__filepath = filepath
        return True

    def _destroy(self) -> None:
        os.remove(self.filepath)

    def write(self, registry_data: list) -> None:
        """
        Writes the registry data list as JSON to the registry file. If no
        file exists, it will create it and write the data. If a file does exist
        it will _overwrite_ everything in it.
        """
        with open(self.__filepath, 'w+') as registry_file:
            registry_file.seek(0)
            registry_file.write(json.dumps(registry_data))
            registry_file.truncate()

    def read(self) -> Union[list, dict]:
        """
        Reads the registry file and parses the JSON and returns a list.
        If the file is empty it will return an empty list.
        If you are modifying or updating the registry file, you _must_ call
        this function first to get the current state to append to the dict or
        modify it because _write_registry_file overwrites the file.
        """
        try:
            with open(self.filepath, 'r') as registry_file:
                self.log.debug("Reading from registrar: filepath {}".format(self.filepath))
                registry_file.seek(0)
                file_data = registry_file.read()
                if file_data:
                    try:
                        registry_data = json.loads(file_data)
                    except JSONDecodeError:
                        raise self.RegistryError(f"Registry contains invalid JSON at '{self.__filepath}'")
                else:
                    registry_data = list() if self._multi_contract else dict()

        except FileNotFoundError:
            raise self.NoRegistry("No registry at filepath: {}".format(self.filepath))

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
        self.write(registry_data)
        self.log.info("Enrolled {}:{} into registry {}".format(contract_name, contract_address, self.filepath))

    def search(self, contract_name: str=None, contract_address: str=None):
        """
        Searches the registry for a contract with the provided name or address
        and returns the contracts component data.
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
            raise self.UnknownContract(contract_name)

        if contract_address and len(contracts) > 1:
            m = "Multiple records returned for address {}"
            self.log.critical(m)
            raise self.IllegalRegistry(m.format(contract_address))

        return contracts if contract_name else contracts[0]


class LocalEthereumContractRegistry(EthereumContractRegistry):

    _default_registry_filepath = os.path.join(
        DEFAULT_CONFIG_ROOT, 'dev_contract_registry.json'
    )

    __filepath = _default_registry_filepath

    @classmethod
    def download_latest_publication(cls, *args, **kwargs):
        return cls._default_registry_filepath


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
        self.temp_filepath = constants.REGISTRY_COMMITTED  # just in case
        self.log.info("Wrote temporary registry to filesystem {}".format(filepath))
        return filepath


class InMemoryEthereumContractRegistry(EthereumContractRegistry):

    def __init__(self) -> None:
        super().__init__(registry_filepath="::memory-registry::")
        self.__registry_data = None  # type: str

    def clear(self):
        self.__registry_data = None

    def _swap_registry(self, filepath: str) -> bool:
        raise NotImplementedError

    def write(self, registry_data: list) -> None:
        self.__registry_data = json.dumps(registry_data)

    def read(self) -> list:
        try:
            registry_data = json.loads(self.__registry_data)
        except TypeError:
            if self.__registry_data is None:
                registry_data = list() if self._multi_contract else dict()
            else:
                raise
        return registry_data

    def commit(self, filepath) -> str:
        """writes the current state of the registry to a file"""
        if 'tmp' not in filepath:
            raise ValueError(f"Filepaths for saving in-memory registries must contain 'tmp'.  Got {filepath}")
        self.log.info("Committing temporary registry to {}".format(filepath))
        with open(filepath, 'w') as file:
            file.write(self.__registry_data)
        self.log.info("Wrote in-memory registry to filesystem {}".format(filepath))
        return filepath


class AllocationRegistry(EthereumContractRegistry):

    _multi_contract = False
    _contract_name = 'UserEscrow'

    _default_registry_filepath = os.path.join(DEFAULT_CONFIG_ROOT, 'allocation_registry.json')

    class NoAllocationRegistry(EthereumContractRegistry.NoRegistry):
        pass

    class AllocationEnrollmentError(RuntimeError):
        pass

    class UnknownBeneficiary(ValueError):
        pass

    def search(self, beneficiary_address: str = None, contract_address: str=None):
        if not (bool(beneficiary_address) ^ bool(contract_address)):
            raise ValueError("Pass contract_owner or contract_address, not both.")

        try:
            allocation_data = self.read()
        except EthereumContractRegistry.NoRegistry:
            raise self.NoAllocationRegistry

        if beneficiary_address:
            try:
                contract_data = allocation_data[beneficiary_address]
            except KeyError:
                raise self.UnknownBeneficiary

        elif contract_address:
            records = list()
            for beneficiary_address, contract_data in allocation_data.items():
                contract_address, contract_abi = contract_data['address'], contract_data['abi']
                records.append(dict(address=contract_address, abi=contract_abi))
            if len(records) > 1:
                raise self.RegistryError("Multiple {} deployments for beneficiary {}".format(self._contract_name, beneficiary_address))
            else:
                contract_data = records[0]

        else:
            raise ValueError("Beneficiary address or contract address must be supplied.")

        return contract_data

    def enroll(self, beneficiary_address, contract_address, contract_abi) -> None:
        contract_data = [contract_address, contract_abi]
        try:
            allocation_data = self.read()
        except self.RegistryError:
            self.log.info("Blank allocation registry encountered: enrolling {}:{}".format(beneficiary_address, contract_address))
            allocation_data = list() if self._multi_contract else dict()  # empty registry

        if beneficiary_address in allocation_data:
            raise self.AllocationEnrollmentError("There is an existing {} deployment for {}".format(self._contract_name, beneficiary_address))

        allocation_data[beneficiary_address] = contract_data
        self.write(allocation_data)
        self.log.info("Enrolled {}:{} into allocation registry {}".format(beneficiary_address, contract_address, self.filepath))


class InMemoryAllocationRegistry(AllocationRegistry):

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(registry_filepath="::memory-registry::", *args, **kwargs)
        self.__registry_data = None  # type: str

    def clear(self):
        self.__registry_data = None

    def _swap_registry(self, filepath: str) -> bool:
        raise NotImplementedError

    def write(self, registry_data: list) -> None:
        self.__registry_data = json.dumps(registry_data)

    def read(self) -> list:
        try:
            registry_data = json.loads(self.__registry_data)
        except TypeError:
            if self.__registry_data is None:
                registry_data = dict()
            else:
                raise
        return registry_data
