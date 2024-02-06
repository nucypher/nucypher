import hashlib
import json
from abc import ABC, abstractmethod
from json import JSONDecodeError
from pathlib import Path
from typing import Dict, List, NamedTuple, Optional, Tuple, Type, Union

import requests
from requests import Response
from web3.types import ABI

from nucypher.blockchain.eth import domains
from nucypher.blockchain.eth.domains import TACoDomain
from nucypher.utilities.logging import Logger

RegistryArtifact = Dict[str, Union[str, ABI]]
RegistryEntry = Dict[str, RegistryArtifact]
RegistryData = Dict[int, RegistryEntry]


class RegistrySource(ABC):

    logger = Logger('RegistrySource')

    name = NotImplementedError
    is_primary = NotImplementedError

    class RegistrySourceError(Exception):
        """Base class for registry source errors"""

    class Invalid(RegistrySourceError):
        """Raised when invalid data is encountered in the registry"""

    class Unavailable(RegistrySourceError):
        """Raised when there are no available registry sources"""

    def __init__(self, domain: TACoDomain, *args, **kwargs):
        if str(domain) not in domains.SUPPORTED_DOMAINS:
            raise ValueError(
                f"{self.__class__.__name__} not available for domain '{domain}'. "
                f"Valid options are: {', '.join(list(domains.SUPPORTED_DOMAINS))}"
            )
        self.domain = domain
        self.data = self.get()

    def __repr__(self) -> str:
        endpoint = self.get_publication_endpoint()
        return f"{self.__class__.__name__}(endpoint={endpoint})"

    @abstractmethod
    def get_publication_endpoint(self) -> str:
        """Get the endpoint for the registry publication."""
        raise NotImplementedError

    @abstractmethod
    def get(self) -> RegistryData:
        """Get the contract registry data from the registry source."""
        raise NotImplementedError


class GithubRegistrySource(RegistrySource):

    _PUBLICATION_REPO = "nucypher/nucypher-contracts"
    _BASE_URL = f'https://raw.githubusercontent.com/{_PUBLICATION_REPO}'

    name = "GitHub Registry Source"
    is_primary = True

    @property
    def registry_name(self) -> str:
        """Get the name of the registry file."""
        name = f"{str(self.domain)}.json"
        return name

    def get_publication_endpoint(self) -> str:
        """Get the GitHub endpoint for the registry publication."""
        url = f"{self._BASE_URL}/main/deployment/artifacts/{self.registry_name}"
        return url

    def decode(self, response: Response, endpoint: str) -> RegistryData:
        """JSON Decode the registry data."""
        try:
            data = response.json()
        except JSONDecodeError:
            raise self.Invalid(f"Invalid registry JSON at '{endpoint}'.")
        return data

    def get(self) -> RegistryData:
        publication_endpoint = self.get_publication_endpoint()
        try:
            self.logger.debug(
                f"Downloading contract registry from {publication_endpoint}"
            )
            response = requests.get(publication_endpoint)
        except requests.exceptions.ConnectionError as e:
            error = f"Failed to fetch registry from {publication_endpoint}: {str(e)}"
            raise self.Unavailable(error)
        if response.status_code != 200:
            error = f"Failed to fetch registry from {publication_endpoint} with status code {response.status_code}"
            raise self.Unavailable(error)
        data = self.decode(response=response, endpoint=publication_endpoint)
        return data


class LocalRegistrySource(RegistrySource):
    """A local contract registry source."""

    name = "Local Registry Source"
    is_primary = False

    def __init__(self, filepath: Path, *args, **kwargs):
        self.filepath = filepath
        super().__init__(*args, **kwargs)

    @property
    def registry_name(self) -> str:
        """Get the name of the registry file."""
        return self.filepath.name

    def get_publication_endpoint(self) -> Path:
        """Get the path to the local contract registry."""
        filepath = Path(self.filepath).absolute()
        return filepath

    def decode(self, data: str, endpoint: str) -> RegistryData:
        """JSON Decode the registry data."""
        try:
            data = json.loads(data)
        except JSONDecodeError:
            raise self.Invalid(f"Invalid registry JSON at '{endpoint}'.")
        return data

    def get(self) -> RegistryData:
        """Get the latest contract registry available from the local filesystem."""
        filepath = self.get_publication_endpoint()
        self.logger.debug(f"Reading registry at {filepath}")
        try:
            with open(filepath, "r") as f:
                data = f.read()
        except IOError as e:
            error = f"Failed to read registry at {filepath.absolute()}: {str(e)}"
            raise self.RegistrySourceError(error)
        if not data:
            raise self.RegistrySourceError(
                f"Registry file '{filepath}' has no content."
            )
        data = self.decode(data=data, endpoint=str(filepath))
        return data


class EmbeddedRegistrySource(LocalRegistrySource):
    name = "Embedded Registry Source"
    is_primary = False

    _CONTRACT_REGISTRY_BASE = Path(__file__).parent / "contract_registry"

    def __init__(self, domain, *args, **kwargs):
        self.domain = domain
        filepath = self.get_publication_endpoint()
        super().__init__(domain=domain, filepath=filepath, *args, **kwargs)

    @property
    def registry_name(self) -> str:
        return f"{str(self.domain)}.json"

    def get_publication_endpoint(self) -> Path:
        """Get the path to the embedded contract registry."""
        filepath = Path(self._CONTRACT_REGISTRY_BASE / self.registry_name).absolute()
        return filepath


class RegistrySourceManager:
    """A chain of registry sources."""

    logger = Logger('RegistrySource')

    _FALLBACK_CHAIN: Tuple[Type[RegistrySource]] = (
        GithubRegistrySource,
        # ...,
        EmbeddedRegistrySource,
    )

    class NoSourcesAvailable(Exception):
        """Raised when there are no available registry sources"""

    def __init__(
        self,
        domain: TACoDomain,
        sources: Optional[List[RegistrySource]] = None,
        only_primary: bool = False,
    ):
        if only_primary and sources:
            raise ValueError("Either use 'only_primary' or 'sources', but not both.")
        elif only_primary:
            self.sources = self.get_primary_sources()
        else:
            self.sources = list(sources or self._FALLBACK_CHAIN)
        self.domain = domain

    @classmethod
    def get_primary_sources(cls) -> List[Type[RegistrySource]]:
        """Get the primary registry sources."""
        return [source for source in cls._FALLBACK_CHAIN if source.is_primary]

    def fetch_latest_publication(self) -> RegistrySource:
        """Get the latest contract registry data available from a registry source chain."""
        for source_class in self.sources:
            try:
                source = source_class(domain=self.domain)
            except RegistrySource.Unavailable:
                self.logger.warn(
                    f"Fetching registry from {source_class.__name__} failed."
                )
                continue
            else:
                if not source.is_primary:
                    message = (
                        f"Warning: {source_class.__name__} is not a primary source."
                    )
                    self.logger.warn(message)
                return source
        self.logger.warn("All known registry sources failed.")
        raise self.NoSourcesAvailable


class ContractRegistry:
    """
    A registry of contract artifacts.
    The registry is a JSON file that maps chain IDs -> contract names -> addresses and ABIs.

    ```json
    {
        1: {
            "ContractName": {
                "address": "0xdeadbeef",
                "abi": [...]
            }
        },
        5: {
            "AnotherContractName": {
                "address": "0xdeadbeef",
                 "abi": [...]
            }
        }
    }
    ```
    """

    class RegistryEntry(NamedTuple):
        """A single contract registry entry."""

        name: str
        address: str
        chain_id: int
        abi: ABI

    logger = Logger('ContractRegistry')

    class RegistryError(Exception):
        """Base class for registry errors"""

    class UnknownContract(RegistryError):
        """Raised when a contract is not found in the registry"""

    class InvalidRegistry(RegistryError):
        """Raised when invalid data is encountered in the registry"""

    class AmbiguousSearchTerms(RegistryError):
        """Raised when there are multiple results for a given registry search"""

    def __init__(self, source: RegistrySource):
        self.log = Logger("registry")
        if not source.data:
            data = source.get()
        else:
            data = source.data
        self._source = source
        self._domain = source.domain
        self._data = data
        self._id = None

    def __eq__(self, other) -> bool:
        return bool(self.id == other.id)

    def __repr__(self) -> str:
        r = f"{self.__class__.__name__}(id={self.id[:6]})"
        return r

    @property
    def id(self) -> str:
        """A unique identifier for this registry."""
        if self._id:
            return self._id
        blake = hashlib.blake2b()
        blake.update(json.dumps(self._data).encode())
        self._id = blake.digest().hex()
        return self._id

    @property
    def source_endpoint(self) -> str:
        """Get the endpoint this registry was sourced from."""
        if not self._source:
            raise self.RegistryError("No registry source available.")
        return self._source.get_publication_endpoint()

    @classmethod
    def from_latest_publication(
        cls,
        domain: TACoDomain,
        source_manager: Optional[RegistrySourceManager] = None,
    ) -> "ContractRegistry":
        """Get the latest contract registry available from a registry source chain."""
        source_manager = source_manager or RegistrySourceManager(domain=domain)
        source = source_manager.fetch_latest_publication()
        registry = cls(source=source)
        return registry

    def search(
        self,
        chain_id: int,
        contract_name: Optional[str] = None,
        contract_address: Optional[str] = None,
    ) -> RegistryEntry:
        """Search the registry for a contract by name or address"""
        if not (bool(contract_name) ^ bool(contract_address)):
            raise ValueError("Pass contract_name or contract_address, not both.")
        registry_data, results = self._data, list()
        for registry_chain_id, contracts in registry_data.items():
            if int(registry_chain_id) != int(chain_id):
                continue
            for registry_contract_name, artifacts in contracts.items():
                name_match = registry_contract_name == contract_name
                address_match = contract_address == artifacts["address"]
                if name_match or address_match:
                    record = self.RegistryEntry(
                        name=registry_contract_name,
                        chain_id=registry_chain_id,
                        address=artifacts["address"],
                        abi=artifacts["abi"],
                    )
                    results.append(record)
        if not results:
            raise self.UnknownContract(contract_name or contract_address)
        elif len(results) > 1:
            search_term = "address" if contract_address else "name"
            result_term = contract_name or contract_address
            raise self.AmbiguousSearchTerms(
                f"Multiple contracts with {search_term} '{result_term}' found."
            )
        result = results[0]
        return result
