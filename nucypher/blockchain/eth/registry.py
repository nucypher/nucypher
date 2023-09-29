import hashlib
import json
from abc import ABC, abstractmethod
from json import JSONDecodeError
from pathlib import Path
from typing import Dict, Iterator, List, Optional, Union

import requests

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
        return str(self.get_publication_endpoint())


class GithubRegistrySource(CanonicalRegistrySource):

    _PUBLICATION_REPO = "nucypher/nucypher"
    _BASE_URL = f'https://raw.githubusercontent.com/{_PUBLICATION_REPO}'

    name = "GitHub Registry Source"
    is_primary = True

    def get_publication_endpoint(self) -> str:
        url = f"{self._BASE_URL}/development/nucypher/blockchain/eth/contract_registry/{self.network}/{self.registry_name}"
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

    def get_publication_endpoint(self) -> Path:
        filepath = Path(CONTRACT_REGISTRY_BASE / self.network / self.registry_name).absolute()
        return filepath

    def fetch_latest_publication(self) -> Union[str, bytes]:
        filepath = self.get_publication_endpoint()
        self.logger.debug(f"Reading registry at {filepath.absolute()}")
        try:
            with open(filepath, "r") as f:
                registry_data = f.read()
            return registry_data
        except IOError as e:
            error = f"Failed to read registry at {filepath.absolute()}: {str(e)}"
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

    logger = Logger('ContractRegistry')

    class RegistryError(Exception):
        """Base class for registry errors"""

    class UnknownContract(RegistryError):
        """Raised when a contract is not found in the registry"""

    class InvalidRegistry(RegistryError):
        """Raised when invalid data is encountered in the registry"""

    def __init__(self, source=None, *args, **kwargs):
        self.__source = source
        self.log = Logger("registry")
        self._id = None

    def __eq__(self, other) -> bool:
        return bool(self.id == other.id)

    def __repr__(self) -> str:
        r = f"{self.__class__.__name__}(id={self.id[:6]})"
        return r

    @property
    def id(self) -> str:
        if not self._id:
            blake = hashlib.blake2b()
            blake.update(json.dumps(self.read()).encode())
            self._id = blake.digest().hex()
        return self._id

    @property
    def source(self) -> 'CanonicalRegistrySource':
        return self.__source

    @abstractmethod
    def read(self) -> Union[list, dict]:
        raise NotImplementedError

    @classmethod
    def from_latest_publication(cls,
                                *args,
                                source_manager: Optional[RegistrySourceManager] = None,
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

    def __init__(self, filepath: Path, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.__filepath = filepath
        self.log.info(f"Using contract registry {filepath}")

    def __repr__(self):
        r = f"{self.__class__.__name__}(filepath={self.filepath})"
        return r

    @property
    def filepath(self) -> Path:
        return self.__filepath

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
                        raise self.InvalidRegistry(f"Registry contains invalid JSON at '{self.__filepath}'")
        except FileNotFoundError:
            raise FileNotFoundError("No registry at filepath: {}".format(self.filepath))
        except JSONDecodeError:
            raise
        return registry_data


class InMemoryContractRegistry(BaseContractRegistry):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.__registry_data = None
        self.filepath = "::memory::"

    def read(self) -> list:
        try:
            registry_data = json.loads(self.__registry_data)
        except TypeError:
            if self.__registry_data is None:
                registry_data = dict()
            else:
                raise
        return registry_data
