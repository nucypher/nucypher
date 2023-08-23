


import json
from contextlib import contextmanager
from typing import Union

from hexbytes import HexBytes

from nucypher.blockchain.eth.clients import EthereumClient
from nucypher.blockchain.eth.networks import NetworksInventory
from nucypher.blockchain.eth.registry import (
    BaseContractRegistry,
    CanonicalRegistrySource,
    RegistrySourceManager,
)
from nucypher.config.constants import TEMPORARY_DOMAIN
from tests.constants import MOCK_ETH_PROVIDER_URI, TESTERCHAIN_CHAIN_ID
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

    real_networks = NetworksInventory.NETWORKS
    real_eth_networks = NetworksInventory.ETH_NETWORKS
    real_poly_networks = NetworksInventory.POLY_NETWORKS
    try:
        RegistrySourceManager._FALLBACK_CHAIN = (MockRegistrySource,)
        NetworksInventory.NETWORKS = (TEMPORARY_DOMAIN,)
        NetworksInventory.ETH_NETWORKS = (TEMPORARY_DOMAIN,)
        NetworksInventory.POLY_NETWORKS = (TEMPORARY_DOMAIN,)
        yield real_networks
    finally:
        NetworksInventory.POLY_NETWORKS = real_poly_networks
        NetworksInventory.ETH_NETWORKS = real_eth_networks
        NetworksInventory.NETWORKS = real_networks


class MockBlockchain(TesterBlockchain):

    ETH_PROVIDER_URI = MOCK_ETH_PROVIDER_URI

    FAKE_TX_HASH = HexBytes(b"FAKE29890FAKE8349804")

    FAKE_RECEIPT = {
        "transactionHash": FAKE_TX_HASH,
        "gasUsed": 1,
        "blockNumber": 1,
        "blockHash": HexBytes(b"FAKE43434343FAKE43443434"),
        "contractAddress": HexBytes(b"0xdeadbeef"),
    }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._mock_client = MockEthereumClient(w3=self.client.w3)
        self.client = self._mock_client

    def wait_for_receipt(
        self, txhash: Union[bytes, str, HexBytes], timeout: int = None
    ) -> dict:
        return self.FAKE_RECEIPT


class MockEthereumClient(EthereumClient):

    def __init__(self, w3):
        super().__init__(w3=w3, node_technology=None, version=None, platform=None, backend=None)

    def add_middleware(self, middleware):
        pass

    @property
    def chain_id(self) -> int:
        return TESTERCHAIN_CHAIN_ID
