import json

from typing import Union

from nucypher.blockchain.eth.constants import PREALLOCATION_ESCROW_CONTRACT_NAME
from nucypher.blockchain.eth.networks import NetworksInventory
from nucypher.blockchain.eth.registry import (BaseContractRegistry, CanonicalRegistrySource,
                                              IndividualAllocationRegistry, RegistrySourceManager)
from nucypher.config.constants import TEMPORARY_DOMAIN
from tests.utils.blockchain import TesterBlockchain
from tests.constants import MOCK_PROVIDER_URI


def make_mock_registry_source_manager(blockchain, test_registry, mock_backend: bool = False):

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

    RegistrySourceManager._FALLBACK_CHAIN = (MockRegistrySource,)
    real_inventory = NetworksInventory.NETWORKS
    NetworksInventory.NETWORKS = (TEMPORARY_DOMAIN,)
    return real_inventory


class MockBlockchain(TesterBlockchain):

    _PROVIDER_URI = MOCK_PROVIDER_URI
    _compiler = None

    def __init__(self):
        super().__init__(mock_backend=True)
