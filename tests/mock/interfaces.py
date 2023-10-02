from typing import Union

from hexbytes import HexBytes

from nucypher.blockchain.eth.clients import EthereumTesterClient
from tests.constants import MOCK_ETH_PROVIDER_URI, TESTERCHAIN_CHAIN_ID
from tests.utils.blockchain import TesterBlockchain


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


class MockEthereumClient(EthereumTesterClient):

    def __init__(self, w3):
        super().__init__(w3=w3, node_technology=None, version=None, platform=None, backend=None)

    def add_middleware(self, middleware):
        pass

    @property
    def chain_id(self) -> int:
        return TESTERCHAIN_CHAIN_ID
