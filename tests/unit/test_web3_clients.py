import datetime
from unittest.mock import Mock, PropertyMock

import pytest
from web3 import HTTPProvider

from nucypher.blockchain.eth.clients import EthereumClient
from nucypher.blockchain.eth.interfaces import BlockchainInterface

DEFAULT_GAS_PRICE = 42
GAS_PRICE_FROM_STRATEGY = 1234
CHAIN_ID = 23


@pytest.mark.parametrize("chain_id_return_value", [hex(CHAIN_ID), CHAIN_ID])
def test_cached_chain_id(mocker, chain_id_return_value):
    web3_mock = mocker.MagicMock()
    mock_client = EthereumClient(w3=web3_mock)

    chain_id_property_mock = PropertyMock(return_value=chain_id_return_value)
    type(web3_mock.eth).chain_id = chain_id_property_mock

    assert mock_client.chain_id == CHAIN_ID
    chain_id_property_mock.assert_called_once()

    assert mock_client.chain_id == CHAIN_ID
    chain_id_property_mock.assert_called_once(), "not called again since cached"

    # second instance of client, but uses the same w3 mock
    mock_client_2 = EthereumClient(
        w3=web3_mock,
    )
    assert mock_client_2.chain_id == CHAIN_ID
    assert (
        chain_id_property_mock.call_count == 2
    ), "additional call since different client instance"

    assert mock_client_2.chain_id == CHAIN_ID
    assert chain_id_property_mock.call_count == 2, "not called again since cached"


class MockGethProvider:
    endpoint_uri = 'http://192.168.9.0:8545'
    client_version = 'Geth/v1.4.11-stable-fed692f6/darwin/go1.7'


class SyncedMockW3Eth:

    # Support older and newer versions of web3 py in-test
    version = 5
    chain_id = hex(5)
    block_number = 5

    def getBlock(self, blockNumber):
        return {
            'timestamp': datetime.datetime.timestamp(datetime.datetime.now() - datetime.timedelta(seconds=25))
        }


class MockedW3GethWithPeers:

    @property
    def admin(self):

        class GethAdmin:

            def peers(self):
                return [1, 2, 3]

        return GethAdmin()


#
# Mock Web3
#

class SyncedMockWeb3:

    net = SyncedMockW3Eth()
    eth = SyncedMockW3Eth()
    geth = MockedW3GethWithPeers()

    def __init__(self, provider):
        self.provider = provider
        self.middleware_onion = Mock()

    @property
    def client_version(self):
        return self.provider.client_version

    @property
    def is_connected(self):
        return lambda: True


#
# Mock Blockchain
#

class BlockchainInterfaceTestBase(BlockchainInterface):

    Web3 = SyncedMockWeb3

    def _configure_registry(self, *args, **kwargs):
        pass

    def _setup_solidity(self, *args, **kwargs):
        pass

    def attach_middleware(self):
        pass


class ProviderTypeTestClient(BlockchainInterfaceTestBase):
    def __init__(self,
                 expected_provider_class,
                 actual_provider_to_attach,
                 *args,
                 **kwargs):
        super().__init__(*args, **kwargs)
        self.expected_provider_class = expected_provider_class
        self.test_provider_to_attach = actual_provider_to_attach

    def _attach_blockchain_provider(self, *args, **kwargs) -> None:
        super()._attach_blockchain_provider(*args, **kwargs)

        # check type
        assert isinstance(self.provider, self.expected_provider_class)

        super()._attach_blockchain_provider(provider=self.test_provider_to_attach)


class GethClientTestBlockchain(BlockchainInterfaceTestBase):

    def _attach_blockchain_provider(self, *args, **kwargs) -> None:
        super()._attach_blockchain_provider(provider=MockGethProvider())


def test_client_no_provider():
    with pytest.raises(BlockchainInterface.NoProvider):
        interface = BlockchainInterfaceTestBase()
        interface.connect()


def test_geth_web3_client():
    interface = GethClientTestBlockchain(endpoint="https://my.geth:8545")
    interface.connect()
    assert isinstance(interface.client, EthereumClient)
    assert interface.client.chain_id == 5  # Hardcoded above


def test_detect_provider_type_http():
    interface = ProviderTypeTestClient(
        endpoint="http://mynode.com:8445",
        expected_provider_class=HTTPProvider,
        actual_provider_to_attach=MockGethProvider(),
    )
    interface.connect()
    assert isinstance(interface.client, EthereumClient)


def test_detect_provider_type_https():
    interface = ProviderTypeTestClient(
        endpoint="https://public-node.io:8445",
        expected_provider_class=HTTPProvider,
        actual_provider_to_attach=MockGethProvider,
    )
    interface.connect()
    assert isinstance(interface.client, EthereumClient)


def test_gas_prices(mocker, mock_ethereum_client):
    web3_mock = mock_ethereum_client.w3

    web3_mock.eth.generate_gas_price = mocker.Mock(side_effect=[None, GAS_PRICE_FROM_STRATEGY])
    type(web3_mock.eth).gas_price = PropertyMock(return_value=DEFAULT_GAS_PRICE)  # See docs of PropertyMock

    assert mock_ethereum_client.gas_price == DEFAULT_GAS_PRICE
    assert mock_ethereum_client.gas_price_for_transaction("there's no gas strategy") == DEFAULT_GAS_PRICE
    assert mock_ethereum_client.gas_price_for_transaction("2nd time is the charm") == GAS_PRICE_FROM_STRATEGY
