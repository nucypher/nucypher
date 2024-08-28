from typing import Optional, Union

from atxm.tx import FutureTx
from hexbytes import HexBytes

from nucypher.blockchain.eth.clients import EthereumClient
from nucypher.blockchain.eth.interfaces import BlockchainInterface
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
        "status": 1,
    }

    FAKE_TX_PARAMS = {
        "type": 0,  # legacy
        "to": HexBytes(b"FAKEFAKEFAKEFAKEFAKEFAKEFAKEFAKEFAKEFAKE"),
        "from": HexBytes(b"FAKEFAKEFAKEFAKEFAKEFAKEFAKEFAKEFAKE"),
        "gas": 1,
        "gasPrice": 1,
        "value": 1,
        "data": b"",
        "nonce": 1,
    }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._mock_client = MockEthereumClient(w3=self.client.w3)
        self.client = self._mock_client

    def wait_for_receipt(
        self, txhash: Union[bytes, str, HexBytes], timeout: int = None
    ) -> dict:
        return self.FAKE_RECEIPT

    @classmethod
    def mock_async_tx(
        cls, async_tx_hooks: Optional[BlockchainInterface.AsyncTxHooks] = None
    ) -> FutureTx:
        future_tx = FutureTx(
            id=1,
            params=cls.FAKE_TX_PARAMS,
        )
        if async_tx_hooks:
            future_tx.on_broadcast = async_tx_hooks.on_broadcast
            future_tx.on_broadcast_failure = async_tx_hooks.on_broadcast_failure
            future_tx.on_fault = async_tx_hooks.on_fault
            future_tx.on_finalized = async_tx_hooks.on_finalized
            future_tx.on_insufficient_funds = async_tx_hooks.on_insufficient_funds

        return future_tx


class MockEthereumClient(EthereumClient):

    def __init__(self, w3):
        super().__init__(w3=w3)

    def add_middleware(self, middleware, **kwargs):
        pass

    def inject_middleware(self, middleware, **kwargs):
        pass

    @property
    def chain_id(self) -> int:
        return TESTERCHAIN_CHAIN_ID
