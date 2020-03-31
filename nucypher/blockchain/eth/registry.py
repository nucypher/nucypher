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
from typing import Union, Iterator, List, Dict, Type, Tuple

import requests
from constant_sorrow.constants import REGISTRY_COMMITTED, NO_REGISTRY_SOURCE
from twisted.logger import Logger

from nucypher.blockchain.eth.networks import NetworksInventory
from nucypher.config.constants import DEFAULT_CONFIG_ROOT
from nucypher.blockchain.eth.constants import PREALLOCATION_ESCROW_CONTRACT_NAME


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
        url = f'{self._BASE_URL}/master/nucypher/blockchain/eth/contract_registry/{self.network}/{self.registry_name}'
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


class InPackageRegistrySource(CanonicalRegistrySource):
    _HERE = os.path.abspath(os.path.dirname(__file__))
    _REGISTRY_DIR = os.path.join(_HERE, "contract_registry")

    name = "In-Package Registry Source"
    is_primary = False

    def get_publication_endpoint(self) -> str:
        filepath = str(os.path.join(self._REGISTRY_DIR, self.network, self.registry_name))
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
        InPackageRegistrySource,
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

    def fetch_latest_publication(self, registry_class, network: str = NetworksInventory.DEFAULT):  # TODO: see #1496
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

    def __init__(self, source=NO_REGISTRY_SOURCE, *args, **kwargs):
        self.__source = source
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
        blake.update(self.__class__.__name__.encode())
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
        entries = iter(record[1] for record in self.read())
        return entries

    def enroll(self, contract_name, contract_address, contract_abi, contract_version) -> None:
        """
        Enrolls a contract to the chain registry by writing the name, address,
        and abi information to the filesystem as JSON.

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
                if len(contract) == 3:
                    name, address, abi = contract
                    version = None
                else:
                    name, version, address, abi = contract
                if contract_name == name and \
                        (contract_version is None or version == contract_version) or \
                        contract_address == address:
                    contracts.append((name, version, address, abi))
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


class AllocationRegistry(LocalContractRegistry):

    _multi_contract = False
    _contract_name = PREALLOCATION_ESCROW_CONTRACT_NAME

    REGISTRY_TYPE = 'allocation'
    REGISTRY_NAME = 'allocation_registry.json'

    _default_registry_filepath = os.path.join(DEFAULT_CONFIG_ROOT, REGISTRY_NAME)

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
            raise ValueError(f"Pass either beneficiary_address or contract_address, not both. "
                             f"Got {beneficiary_address} and {contract_address}.")

        try:
            allocation_data = self.read()
        except BaseContractRegistry.NoRegistry:
            raise self.NoAllocationRegistry

        if beneficiary_address:
            try:
                contract_data = allocation_data[beneficiary_address]
                result = contract_data
            except KeyError:
                raise self.UnknownBeneficiary

        elif contract_address:
            records = list()
            for beneficiary_address, contract_data in allocation_data.items():
                if contract_address == contract_data[0]:
                    contract_abi = contract_data[1]
                    records.append([beneficiary_address, contract_abi])
            if len(records) > 1:
                raise self.RegistryError(f"Multiple {self._contract_name} deployments found ({len(records)}) "
                                         f"for contract address {contract_address}")
            elif not records:
                raise self.UnknownContract(f"No {self._contract_name} deployments found "
                                           f"for contract address {contract_address}")
            else:
                result = records[0]

        return result

    def is_beneficiary_enrolled(self, beneficiary_address: str) -> bool:
        try:
            _ = self.search(beneficiary_address=beneficiary_address)
            return True
        except (self.UnknownBeneficiary, self.NoAllocationRegistry):
            return False
        # TODO: #1513 Needs a test for false case (improve unit tests for allocation registry)

    def enroll(self, beneficiary_address, contract_address, contract_abi) -> None:
        contract_data = [contract_address, contract_abi]
        try:
            allocation_data = self.read()
        except self.RegistryError as e:
            self.log.info(f"Failure while reading allocation registry when "
                          f"enrolling {beneficiary_address} ({contract_address}): {e}")
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

    def write(self, registry_data: dict) -> None:
        self.__registry_data = json.dumps(registry_data)

    def read(self) -> dict:
        try:
            registry_data = json.loads(self.__registry_data)
        except TypeError:
            if self.__registry_data is None:
                registry_data = dict()
            else:
                raise
        return registry_data


class IndividualAllocationRegistry(InMemoryAllocationRegistry):

    REGISTRY_NAME = "individual_allocation_ABI.json"

    def __init__(self,
                 beneficiary_address: str,
                 contract_address: str,
                 contract_abi=None,
                 network: str = NetworksInventory.DEFAULT,  # TODO: See #1496
                 *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.beneficiary_address = beneficiary_address
        self.contract_address = contract_address

        source_manager = RegistrySourceManager()

        if not contract_abi:
            # Download individual allocation template to extract contract_abi
            template_data, self.__source = source_manager.fetch_latest_publication(registry_class=self.__class__,
                                                                                   network=network)
            individual_allocation_template = json.loads(template_data)
            if len(individual_allocation_template) != 1:
                raise self.InvalidRegistry("Individual allocation template must contain a single entry")
            try:
                contract_data = individual_allocation_template["BENEFICIARY_ADDRESS"]
            except KeyError:
                raise self.InvalidRegistry("Bad format of individual allocation template. "
                                           "Expected a 'BENEFICIARY_ADDRESS' key.")
            contract_abi = contract_data[1]

        # Fill template with beneficiary and contract addresses
        individual_allocation = {beneficiary_address: [contract_address, contract_abi]}
        self.write(registry_data=individual_allocation)

    @classmethod
    def from_allocation_file(cls, filepath: str, **kwargs) -> 'IndividualAllocationRegistry':
        with open(filepath) as file:
            individual_allocation_file_data = json.load(file)

        registry = cls(**individual_allocation_file_data, **kwargs)
        return registry
