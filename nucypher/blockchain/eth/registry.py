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
import json
from json import JSONDecodeError
from os.path import abspath, dirname

import hashlib
import os
import requests
import shutil
import tempfile
from abc import ABC, abstractmethod
from constant_sorrow.constants import REGISTRY_COMMITTED
from typing import Dict, Iterator, List, Tuple, Type, Union

from nucypher.blockchain.eth import CONTRACT_REGISTRY_BASE
from nucypher.blockchain.eth.networks import NetworksInventory
from nucypher.config.constants import DEFAULT_CONFIG_ROOT
from nucypher.utilities.logging import Logger


class CanonicalRegistrySource(ABC):

    logger = Logger('RegistrySource')

    name = NotImplementedError
    is_primary = NotImplementedError

    def __init__(self, network: str, registry_name: str, *args, **kwargs):
        if network not in NetworksInventory.NETWORKS:
            raise ValueError(f"{self.__class__.__name__} not available for network '{network}'. "
                             f"Valid options are: {list(NetworksInventory.NETWORKS)}")
        self.network = network
        self.registry_name = registry_name

    class RegistrySourceError(Exception):
        pass

    class RegistrySourceUnavailable(RegistrySourceError):
        pass

    @abstractmethod
    def get_publication_endpoint(self) -> str:
        raise NotImplementedError

    @abstractmethod
    def fetch_latest_publication(self) -> Union[str, bytes]:
        raise NotImplementedError

    def __repr__(self):
        return self.get_publication_endpoint()


class GithubRegistrySource(CanonicalRegistrySource):

    _PUBLICATION_REPO = "nucypher/nucypher"
    _BASE_URL = f'https://raw.githubusercontent.com/{_PUBLICATION_REPO}'

    name = "GitHub Registry Source"
    is_primary = True

    def get_publication_endpoint(self) -> str:
        url = f'{self._BASE_URL}/main/nucypher/blockchain/eth/contract_registry/{self.network}/{self.registry_name}'
        return url

    def fetch_latest_publication(self) -> Union[str, bytes]:
        # Setup
        publication_endpoint = self.get_publication_endpoint()
        self.logger.debug(f"Downloading contract registry from {publication_endpoint}")
        try:
            # Fetch
            response = requests.get(publication_endpoint)
        except requests.exceptions.ConnectionError as e:
            error = f"Failed to fetch registry from {publication_endpoint}: {str(e)}"
            raise self.RegistrySourceUnavailable(error)

        if response.status_code != 200:
            error = f"Failed to fetch registry from {publication_endpoint} with status code {response.status_code}"
            raise self.RegistrySourceUnavailable(error)

        registry_data = response.content
        return registry_data


class EmbeddedRegistrySource(CanonicalRegistrySource):

    name = "Embedded Registry Source"
    is_primary = False

    def get_publication_endpoint(self) -> str:
        filepath = str(CONTRACT_REGISTRY_BASE / self.network / self.registry_name)
        return filepath

    def fetch_latest_publication(self) -> Union[str, bytes]:
        filepath = self.get_publication_endpoint()
        self.logger.debug(f"Reading registry at {filepath}")
        try:
            with open(filepath, "r") as f:
                registry_data = f.read()
            return registry_data
        except IOError as e:
            error = f"Failed to read registry at {filepath}: {str(e)}"
            raise self.RegistrySourceError(error)


class RegistrySourceManager:
    logger = Logger('RegistrySource')

    _REMOTE_SOURCES = (
        GithubRegistrySource,
        # TODO: Mirror/fallback for contract registry: moar remote sources - #1454
        # NucypherServersRegistrySource,
        # IPFSRegistrySource,
    )  # type: Tuple[Type[CanonicalRegistrySource]]

    _LOCAL_SOURCES = (
        EmbeddedRegistrySource,
    )  # type: Tuple[Type[CanonicalRegistrySource]]

    _FALLBACK_CHAIN = _REMOTE_SOURCES + _LOCAL_SOURCES

    class NoSourcesAvailable(Exception):
        pass

    def __init__(self, sources=None, only_primary: bool = False):
        if only_primary and sources:
            raise ValueError("Either use 'only_primary' or 'sources', but not both.")
        elif only_primary:
            self.sources = self.get_primary_sources()
        else:
            self.sources = list(sources or self._FALLBACK_CHAIN)

    def __getitem__(self, index):
        return self.sources

    @classmethod
    def get_primary_sources(cls):
        return [source for source in cls._FALLBACK_CHAIN if source.is_primary]

    def fetch_latest_publication(self, registry_class, network: str):
        """
        Get the latest contract registry data available from a registry source chain.
        """

        for registry_source_class in self.sources:
            if isinstance(registry_source_class, CanonicalRegistrySource):  # i.e., it's not a class, but an instance
                registry_source = registry_source_class
                expected = registry_class.REGISTRY_NAME, network
                actual = registry_source.registry_name, registry_source.network
                if actual != expected:
                    raise ValueError(f"(registry_name, network) should be {expected} but got {actual}")
            else:
                registry_source = registry_source_class(network=network, registry_name=registry_class.REGISTRY_NAME)

            try:
                if not registry_source.is_primary:
                    message = f"Warning: Registry at {registry_source} is not a primary source."
                    self.logger.warn(message)
                registry_data_bytes = registry_source.fetch_latest_publication()
            except registry_source.RegistrySourceUnavailable:
                message = f"Fetching registry from {registry_source} failed."
                self.logger.warn(message)
                continue
            else:
                return registry_data_bytes, registry_source
        else:
            self.logger.warn("All known registry sources failed.")
            raise self.NoSourcesAvailable


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
    REGISTRY_NAME = 'contract_registry.json'  # TODO: #1511 Save registry with ID-time-based filename
    DEVELOPMENT_REGISTRY_NAME = 'dev_contract_registry.json'

    class RegistryError(Exception):
        pass

    class EmptyRegistry(RegistryError):
        pass

    class NoRegistry(RegistryError):
        pass

    class UnknownContract(RegistryError):
        pass

    class InvalidRegistry(RegistryError):
        """Raised when invalid data is encountered in the registry"""

    class CantOverwriteRegistry(RegistryError):
        pass

    def __init__(self, source=None, *args, **kwargs):
        self.__source = source
        self.log = Logger("registry")
        self._id = None

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
        if not self._id:
            blake = hashlib.blake2b()
            blake.update(json.dumps(self.read()).encode())
            self._id = blake.digest().hex()
        return self._id

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
    def from_latest_publication(cls,
                                *args,
                                source_manager=None,
                                network: str = NetworksInventory.DEFAULT,
                                **kwargs) -> 'BaseContractRegistry':
        """
        Get the latest contract registry available from a registry source chain.
        """
        if not source_manager:
            source_manager = RegistrySourceManager()

        registry_data, source = source_manager.fetch_latest_publication(registry_class=cls, network=network)

        registry_instance = cls(*args, source=source, **kwargs)
        registry_instance.write(registry_data=json.loads(registry_data))
        return registry_instance

    @property
    def source(self) -> 'CanonicalRegistrySource':
        return self.__source

    @property
    def enrolled_names(self) -> Iterator:
        entries = iter(record[0] for record in self.read())
        return entries

    @property
    def enrolled_addresses(self) -> Iterator:
        entries = iter(record[2] for record in self.read())
        return entries

    def enroll(self, contract_name, contract_address, contract_abi, contract_version) -> None:
        """
        Enrolls a contract to the chain registry by writing the name, version,
        address, and abi information to the filesystem as JSON.

        Note: Unless you are developing NuCypher, you most likely won't ever
        need to use this.
        """
        contract_data = [contract_name, contract_version, contract_address, contract_abi]
        try:
            registry_data = self.read()
        except self.RegistryError:
            self.log.info("Blank registry encountered: enrolling {}:{}:{}"
                          .format(contract_name, contract_version, contract_address))
            registry_data = list()  # empty registry

        registry_data.append(contract_data)
        self.write(registry_data)
        self.log.info("Enrolled {}:{}:{} into registry.".format(contract_name, contract_version, contract_address))

    def search(self, contract_name: str = None, contract_version: str = None, contract_address: str = None) -> tuple:
        """
        Searches the registry for a contract with the provided name or address
        and returns the contracts component data.
        """
        if not (bool(contract_name) ^ bool(contract_address)):
            raise ValueError("Pass contract_name or contract_address, not both.")
        if bool(contract_version) and not bool(contract_name):
            raise ValueError("Pass contract_version together with contract_name.")

        contracts = list()
        registry_data = self.read()

        try:
            for contract in registry_data:
                name, version, address, abi = contract
                if contract_address == address or \
                        contract_name == name and (contract_version is None or version == contract_version):
                    contracts.append(contract)
        except ValueError:
            message = "Missing or corrupted registry data"
            self.log.critical(message)
            raise self.InvalidRegistry(message)

        if not contracts:
            raise self.UnknownContract(contract_name)

        if contract_address and len(contracts) > 1:
            m = f"Multiple records returned for address {contract_address}"
            self.log.critical(m)
            raise self.InvalidRegistry(m)

        result = tuple(contracts) if contract_name else contracts[0]
        return result


class LocalContractRegistry(BaseContractRegistry):

    REGISTRY_TYPE = 'contract'

    def __init__(self, filepath: str, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.__filepath = filepath
        self.log.info(f"Using {self.REGISTRY_TYPE} registry {filepath}")

    def __repr__(self):
        r = f"{self.__class__.__name__}(filepath={self.filepath})"
        return r

    @property
    def filepath(self) -> str:
        return str(self.__filepath)

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
                self.log.debug("Reading from registry: filepath {}".format(self.filepath))
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

    def write(self, registry_data: Union[List, Dict]) -> None:
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

        self._id = None

    def _destroy(self) -> None:
        os.remove(self.filepath)

    @classmethod
    def from_dict(cls, payload: dict, **overrides) -> 'LocalContractRegistry':
        payload.update({k: v for k, v in overrides.items() if v is not None})
        registry = cls(filepath=payload['filepath'])
        return registry

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
        self._id = None

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
            filepath = os.path.join(DEFAULT_CONFIG_ROOT, self.REGISTRY_NAME)
        self.log.info("Committing in-memory registry to disk.")
        if os.path.exists(filepath) and not overwrite:
            existing_registry = LocalContractRegistry(filepath=filepath)
            raise self.CantOverwriteRegistry(f"Registry #{existing_registry.id[:16]} exists at {filepath} "
                                             f"while writing Registry #{self.id[:16]}).  "
                                             f"Pass overwrite=True to force it.")
        with open(filepath, 'w') as file:
            file.write(self.__registry_data)
        self.log.info("Wrote in-memory registry to '{}'".format(filepath))
        return filepath

    def _destroy(self) -> None:
        self.__registry_data = dict()
