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
import hashlib
import json
import os
import shutil
import tempfile
from abc import ABC, abstractmethod
from json import JSONDecodeError
from os.path import dirname, abspath
from typing import Union, Iterator

import requests
from constant_sorrow.constants import REGISTRY_COMMITTED
from twisted.logger import Logger
from web3.contract import Contract

from nucypher.config.constants import DEFAULT_CONFIG_ROOT


class BaseContractRegistry(ABC):
    """
    Records known contracts on the disk for future access and utility. This
    lazily writes to the filesystem during contract enrollment.

    WARNING: Unless you are developing NuCypher, you most likely won't ever need
    to use this.
    """

    logger = Logger('ContractRegistry')

    _multi_contract = True
    _contract_name = NotImplemented

    # Registry
    REGISTRY_NAME = 'contract_registry.json'  # TODO: Save registry with ID-time-based filename
    DEVELOPMENT_REGISTRY_NAME = 'dev_contract_registry.json'

    __PUBLICATION_USER = "nucypher"
    __PUBLICATION_REPO = f"{__PUBLICATION_USER}/ethereum-contract-registry"
    __PUBLICATION_BRANCH = 'goerli'          # TODO: Allow other branches to be used
    PUBLICATION_ENDPOINT = f'https://raw.githubusercontent.com/{__PUBLICATION_REPO}/{__PUBLICATION_BRANCH}/{REGISTRY_NAME}'

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

    def __init__(self, *args, **kwargs):
        self.log = Logger("registry")

    def __eq__(self, other) -> bool:
        if self is other:
            return True  # and that's all
        return bool(self.id == other.id)

    def __repr__(self) -> str:
        r = f"{self.__class__.__name__}(id={self.id[:6]})"
        return r

    @property
    def id(self) -> str:
        """Returns a hexstr of the registry contents."""
        blake = hashlib.blake2b()
        blake.update(json.dumps(self.read()).encode())
        digest = blake.digest().hex()
        return digest

    @abstractmethod
    def _destroy(self) -> None:
        raise NotImplementedError

    @abstractmethod
    def write(self, registry_data: list) -> None:
        raise NotImplementedError

    @abstractmethod
    def read(self) -> Union[list, dict]:
        raise NotImplementedError

    @classmethod
    def fetch_latest_publication(cls) -> bytes:
        """
        Get the latest published contract registry from github and save it on the local file system.
        """

        # Setup
        cls.logger.debug(f"Downloading contract registry from {cls.PUBLICATION_ENDPOINT}")
        response = requests.get(cls.PUBLICATION_ENDPOINT)

        # Fetch
        if response.status_code != 200:
            error = f"Failed to fetch registry from {cls.PUBLICATION_ENDPOINT} with status code {response.status_code}"
            raise cls.RegistrySourceUnavailable(error)

        registry_data = response.content
        return registry_data

    @classmethod
    def from_latest_publication(cls, *args, **kwargs) -> 'BaseContractRegistry':
        registry_data_bytes = cls.fetch_latest_publication()
        instance = cls(*args, **kwargs)
        instance.write(registry_data=json.loads(registry_data_bytes))
        return instance

    @property
    def enrolled_names(self) -> Iterator:
        entries = iter(record[0] for record in self.read())
        return entries

    @property
    def enrolled_addresses(self) -> Iterator:
        entries = iter(record[1] for record in self.read())
        return entries

    def enroll(self, contract_name, contract_address, contract_abi) -> None:
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
        self.log.info("Enrolled {}:{} into registry.".format(contract_name, contract_address))

    def search(self, contract_name: str = None, contract_address: str = None) -> tuple:
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
            message = "Missing or corrupted registry data"
            self.log.critical(message)
            raise self.IllegalRegistry(message)

        if not contracts:
            raise self.UnknownContract(contract_name)

        if contract_address and len(contracts) > 1:
            m = "Multiple records returned for address {}"
            self.log.critical(m)
            raise self.IllegalRegistry(m.format(contract_address))

        result = tuple(contracts) if contract_name else contracts[0]
        return result


class LocalContractRegistry(BaseContractRegistry):

    def __init__(self, filepath: str, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.__filepath = filepath
        self.log.info("Using contract registry {}".format(self.__filepath))

    def __repr__(self):
        r = f"{self.__class__.__name__}(filepath={self.filepath})"
        return r

    @property
    def filepath(self) -> str:
        return self.__filepath

    def _swap_registry(self, filepath: str) -> bool:
        self.__filepath = filepath
        return True

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

    def write(self, registry_data: list) -> None:
        """
        Writes the registry data list as JSON to the registry file. If no
        file exists, it will create it and write the data. If a file does exist
        it will _overwrite_ everything in it.
        """
        # Ensure parent path exists
        os.makedirs(abspath(dirname(self.__filepath)), exist_ok=True)

        with open(self.__filepath, 'w') as registry_file:
            registry_file.seek(0)
            registry_file.write(json.dumps(registry_data))
            registry_file.truncate()

    def _destroy(self) -> None:
        os.remove(self.filepath)

    @classmethod
    def from_dict(cls, payload: dict, **overrides) -> 'LocalContractRegistry':
        payload.update({k: v for k, v in overrides.items() if v is not None})
        blockchain = cls(filepath=payload['filepath'])
        return blockchain

    def to_dict(self) -> dict:
        payload = dict(filepath=self.__filepath)
        return payload


class TemporaryContractRegistry(LocalContractRegistry):

    def __init__(self, *args, **kwargs) -> None:
        _, self.temp_filepath = tempfile.mkstemp()
        super().__init__(filepath=self.temp_filepath, *args, **kwargs)

    def clear(self):
        self.log.info("Cleared temporary registry at {}".format(self.filepath))
        with open(self.filepath, 'w') as registry_file:
            registry_file.write('')

    def commit(self, filepath) -> str:
        """writes the current state of the registry to a file"""
        self.log.info("Committing temporary registry to {}".format(filepath))
        self._swap_registry(filepath)                     # I'll allow it

        if os.path.exists(filepath):
            self.log.debug("Removing registry {}".format(filepath))
            self.clear()                                  # clear prior sim runs

        _ = shutil.copy(self.temp_filepath, filepath)
        self.temp_filepath = REGISTRY_COMMITTED  # just in case
        self.log.info("Wrote temporary registry to filesystem {}".format(filepath))
        return filepath


class InMemoryContractRegistry(BaseContractRegistry):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.__registry_data = None
        self.filepath = "::memory::"

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

    def commit(self, filepath: str = None, overwrite: bool = False) -> str:
        """writes the current state of the registry to a file"""
        if not filepath:
            filepath = os.path.join(DEFAULT_CONFIG_ROOT, self.REGISTRY_NAME)  # TODO: Use ID-based filename
        self.log.info("Committing in-memory registry to disk.")
        if os.path.exists(filepath) and not overwrite:
            existing_registry = LocalContractRegistry(filepath=filepath)
            raise self.RegistryError(f"Registry #{existing_registry.id[:16]} exists at {filepath} "
                                     f"while writing Registry #{self.id[:16]}).  "
                                     f"Pass overwrite=True to force it.")
        with open(filepath, 'w') as file:
            file.write(self.__registry_data)
        self.log.info("Wrote in-memory registry to '{}'".format(filepath))
        return filepath

    def _destroy(self) -> None:
        self.__registry_data = dict()


class AllocationRegistry(LocalContractRegistry):

    _multi_contract = False
    _contract_name = 'UserEscrow'

    _default_registry_filepath = os.path.join(DEFAULT_CONFIG_ROOT, 'allocation_registry.json')

    class NoAllocationRegistry(BaseContractRegistry.NoRegistry):
        pass

    class AllocationEnrollmentError(RuntimeError):
        pass

    class UnknownBeneficiary(ValueError):
        pass

    def __init__(self, filepath: str = None, *args, **kwargs):
        super().__init__(filepath=filepath or self._default_registry_filepath, *args, **kwargs)

    def search(self, beneficiary_address: str = None, contract_address: str = None):
        if not (bool(beneficiary_address) ^ bool(contract_address)):
            raise ValueError("Pass contract_owner or contract_address, not both.")

        try:
            allocation_data = self.read()
        except BaseContractRegistry.NoRegistry:
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
        super().__init__(filepath="::memory-registry::", *args, **kwargs)
        self.__registry_data = None

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
