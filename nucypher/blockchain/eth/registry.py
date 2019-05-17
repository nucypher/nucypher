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
    __PUBLICATION_REPO = "nucypher/ethereum-contract-registry"
    __PUBLICATION_FILENAME = "contract_registry.json"  # TODO: Versioning

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

    def __init__(self, registry_filepath: str = None) -> None:
        self.log = Logger("registry")
        self.__filepath = registry_filepath or self._default_registry_filepath

    @classmethod
    def download_latest_publication(cls,
                                    filepath: str = None,
                                    branch: str = 'goerli'
                                    ) -> str:
        """
        Get the latest published contract registry from github and save it on the local file system.
        """
        from nucypher.config.node import NodeConfiguration

        github_endpoint = f'https://raw.githubusercontent.com/{cls.__PUBLICATION_REPO}/{branch}/{cls.__PUBLICATION_FILENAME}'
        response = requests.get(github_endpoint)
        if response.status_code != 200:
            raise cls.RegistryError(f"Failed to fetch registry from {github_endpoint} with status code {response.status_code} ")

        filepath = filepath or cls._default_registry_filepath
        # TODO : Use envvar for config root and registry path
        try:
            with open(filepath, 'wb') as registry_file:  # TODO: Skip re-write if already up to date
                registry_file.write(response.content)
        except FileNotFoundError:
            raise NodeConfiguration.NoConfigurationRoot
        return filepath

    @classmethod
    def from_latest_publication(cls,
                                filepath: str = None,
                                branch: str = 'goerli'
                                ) -> 'EthereumContractRegistry':
        filepath = cls.download_latest_publication(filepath=filepath, branch=branch)
        instance = cls(registry_filepath=filepath)
        return instance

    def publish(self, branch: str = 'goerli') -> dict:
        # TODO: NuCypher Org GPG Signed Commits?

        #
        # Build Request
        #

        try:
            github_token = os.environ['GITHUB_API_TOKEN']
        except KeyError:
            raise self.RegistryError("Please set the 'GITHUB_API_TOKEN' environment variable and try again.")

        base_url = "api.github.com/repos"
        headers = {"Authorization": f"token {github_token}"}
        github_endpoint = f"https://{base_url}/{self.__PUBLICATION_REPO}/contents/{self.__PUBLICATION_FILENAME}"

        # Encode registry
        with open(self.filepath, "rb") as registry_file:
            base64_registry = base64.b64encode(registry_file.read())

        #
        # Transmit
        #

        # [GET] -> latest commit
        response = requests.get(url=github_endpoint, params={'ref': branch}, headers=headers)
        if response.status_code != 200:
            message = f"Failed to fetch registry from {github_endpoint} with status code {response.status_code}."
            raise self.RegistryError(message)
        response_data = response.json()
        latest_sha = response_data['sha']

        # Compare local vs. remote file contents
        existing_content = base64_registry.decode('utf-8').strip('\n')
        latest_content = response_data['content'].strip('\n')  # GH adds newlines for whatever reason
        if existing_content != latest_content:

            # Update needed... Encode Upload Request
            message = json.dumps({"message": "[automated]",  # TODO: Better commit message including versioning
                                  "branch": branch,
                                  "content": base64_registry.decode("utf-8"),
                                  "sha": latest_sha})

            # [PUT] -> Update Registry and Commit
            headers.update({"Content-Type": "application/json"})
            response = requests.put(url=github_endpoint, data=message, headers=headers)  # TODO: Error handling
            response_data = response.json()
            return response_data

        else:
            raise self.RegistryError(f"Already up to date with {latest_sha}")

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
            with open(self.__filepath, 'r') as registry_file:
                self.log.debug("Reading from registrar: filepath {}".format(self.__filepath))
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
            raise self.UnknownContract(": {}".format(contract_name))

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
