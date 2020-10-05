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

from eth_account.account import Account
from typing import Union, List

from nucypher.blockchain.eth.clients import EthereumClient
from nucypher.blockchain.eth.constants import PREALLOCATION_ESCROW_CONTRACT_NAME
from nucypher.blockchain.eth.networks import NetworksInventory
from nucypher.blockchain.eth.registry import (
    BaseContractRegistry,
    CanonicalRegistrySource,
    IndividualAllocationRegistry,
    RegistrySourceManager
)
from nucypher.config.constants import TEMPORARY_DOMAIN
from tests.constants import MOCK_PROVIDER_URI
from tests.utils.blockchain import TesterBlockchain
from tests.mock.web3 import MockWeb3


@contextmanager
def mock_registry_source_manager(blockchain, test_registry, mock_backend: bool = False):

    class MockRegistrySource(CanonicalRegistrySource):
        name = "Mock Registry Source"
        is_primary = False

        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            if self.network != TEMPORARY_DOMAIN:
                raise ValueError(f"Somehow, MockRegistrySource is trying to get a registry for '{self.network}'. "
                                 f"Only '{TEMPORARY_DOMAIN}' is supported.'")

            if not mock_backend:
                factory = blockchain.get_contract_factory(contract_name=PREALLOCATION_ESCROW_CONTRACT_NAME)
                preallocation_escrow_abi = factory.abi
                self.allocation_template = {
                    "BENEFICIARY_ADDRESS": ["ALLOCATION_CONTRACT_ADDRESS", preallocation_escrow_abi]
                }

        def get_publication_endpoint(self) -> str:
            return f":mock-registry-source:/{self.network}/{self.registry_name}"

        def fetch_latest_publication(self) -> Union[str, bytes]:
            self.logger.debug(f"Reading registry at {self.get_publication_endpoint()}")
            if self.registry_name == BaseContractRegistry.REGISTRY_NAME:
                registry_data = test_registry.read()
            elif self.registry_name == IndividualAllocationRegistry.REGISTRY_NAME:
                registry_data = self.allocation_template
            raw_registry_data = json.dumps(registry_data)
            return raw_registry_data

    real_inventory = NetworksInventory.NETWORKS
    try:
        RegistrySourceManager._FALLBACK_CHAIN = (MockRegistrySource,)
        NetworksInventory.NETWORKS = (TEMPORARY_DOMAIN,)
        yield real_inventory
    finally:
        NetworksInventory.NETWORKS = real_inventory


class MockEthereumClient(EthereumClient):

    __accounts = dict()

    def __init__(self, w3):
        super().__init__(w3, None, None, None, None)

    def create_account(self):
        account = Account.create()
        self.__accounts[account.address] = account
        return account

    @property
    def accounts(self):
        return list(self.__accounts)

    @property
    def is_local(self):
        return True


class MockBlockchain(TesterBlockchain):

    _PROVIDER_URI = MOCK_PROVIDER_URI
    _compiler = None
    w3 = MockWeb3()

    def __init__(self):
        client = MockEthereumClient(w3=self.w3)
        super().__init__(mock_backend=True, client=client)

    def _generate_insecure_unlocked_accounts(self, quantity: int) -> List[str]:
        addresses = list()
        for _ in range(quantity):
            account = self.client.create_account()
            addresses.append(account.address)
            self._test_account_cache.append(account.address)
            self.log.info('Generated new insecure account {}'.format(account.address))
        return addresses
