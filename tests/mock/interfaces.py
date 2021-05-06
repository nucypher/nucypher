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

from contextlib import contextmanager
from typing import Union

from nucypher.blockchain.eth.clients import EthereumClient
from nucypher.blockchain.eth.networks import NetworksInventory
from nucypher.blockchain.eth.registry import (
    BaseContractRegistry,
    CanonicalRegistrySource,
    RegistrySourceManager
)
from nucypher.config.constants import TEMPORARY_DOMAIN
from tests.constants import MOCK_PROVIDER_URI
from tests.utils.blockchain import TesterBlockchain


@contextmanager
def mock_registry_source_manager(test_registry):

    class MockRegistrySource(CanonicalRegistrySource):
        name = "Mock Registry Source"
        is_primary = False

        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            if self.network != TEMPORARY_DOMAIN:
                raise ValueError(f"Somehow, MockRegistrySource is trying to get a registry for '{self.network}'. "
                                 f"Only '{TEMPORARY_DOMAIN}' is supported.'")

        def get_publication_endpoint(self) -> str:
            return f":mock-registry-source:/{self.network}/{self.registry_name}"

        def fetch_latest_publication(self) -> Union[str, bytes]:
            self.logger.debug(f"Reading registry at {self.get_publication_endpoint()}")
            if self.registry_name == BaseContractRegistry.REGISTRY_NAME:
                registry_data = test_registry.read()
            raw_registry_data = json.dumps(registry_data)
            return raw_registry_data

    real_inventory = NetworksInventory.NETWORKS
    try:
        RegistrySourceManager._FALLBACK_CHAIN = (MockRegistrySource,)
        NetworksInventory.NETWORKS = (TEMPORARY_DOMAIN,)
        yield real_inventory
    finally:
        NetworksInventory.NETWORKS = real_inventory


class MockBlockchain(TesterBlockchain):

    PROVIDER_URI = MOCK_PROVIDER_URI

    def __init__(self):
        super().__init__(compile_now=False)


class MockEthereumClient(EthereumClient):

    def __init__(self, w3):
        super().__init__(w3=w3, node_technology=None, version=None, platform=None, backend=None)

    def connect(self, *args, **kwargs) -> bool:
        if 'compile_now' in kwargs:
            raise ValueError("Mock testerchain cannot handle solidity source compilation.")
        return super().connect(compile_now=False, *args, **kwargs)
