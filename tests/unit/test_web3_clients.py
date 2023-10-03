

import datetime
from unittest.mock import Mock, PropertyMock

import pytest
from web3 import HTTPProvider, IPCProvider, WebsocketProvider

from nucypher.blockchain.eth.clients import (
    AlchemyClient,
    GanacheClient,
    GethClient,
    InfuraClient,
    ParityClient,
)
from nucypher.blockchain.eth.interfaces import BlockchainInterface
from nucypher.utilities.networking import LOOPBACK_ADDRESS

DEFAULT_GAS_PRICE = 42
GAS_PRICE_FROM_STRATEGY = 1234

#
# Mock Providers
#


class MockGethProvider:
    endpoint_uri = 'file:///ipc.geth'
    client_version = 'Geth/v1.4.11-stable-fed692f6/darwin/go1.7'


class MockParityProvider:
    endpoint_uri = 'file:///ipc.parity'
    client_version = 'Parity-Ethereum/v2.5.1-beta-e0141f8-20190510/x86_64-linux-gnu/rustc1.34.1'


class MockGanacheProvider:
    endpoint_uri = 'http://ganache:8445'
    client_version = 'EthereumJS TestRPC/v2.1.5/ethereum-js'


class MockInfuraProvider:
    endpoint_uri = 'wss://:@goerli.infura.io/ws/v3/1234567890987654321abcdef'
    client_version = 'Geth/v1.8.23-omnibus-2ad89aaa/linux-amd64/go1.11.1'


class MockAlchemyProvider:
    endpoint_uri = 'https://eth-rinkeby.alchemyapi.io/v2/1234567890987654321abcdef'
    client_version = 'Geth/v1.9.20-stable-979fc968/linux-amd64/go1.15'


class MockWebSocketProvider:
    endpoint_uri = f'ws://{LOOPBACK_ADDRESS}:8546'
    client_version = 'Geth/v1.8.23-omnibus-2ad89aaa/linux-amd64/go1.11.1'


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


class MockedW3GethWithNoPeers:

    @property
    def admin(self):

        class GethAdmin:

            def peers(self):
                return []

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


class InfuraTestClient(BlockchainInterfaceTestBase):

    def _attach_blockchain_provider(self, *args, **kwargs) -> None:
        super()._attach_blockchain_provider(provider=MockInfuraProvider())


class AlchemyTestClient(BlockchainInterfaceTestBase):

    def _attach_blockchain_provider(self, *args, **kwargs) -> None:
        super()._attach_blockchain_provider(provider=MockAlchemyProvider())


class GethClientTestBlockchain(BlockchainInterfaceTestBase):

    def _attach_blockchain_provider(self, *args, **kwargs) -> None:
        super()._attach_blockchain_provider(provider=MockGethProvider())


class ParityClientTestInterface(BlockchainInterfaceTestBase):

    def _attach_blockchain_provider(self, *args, **kwargs) -> None:
        super()._attach_blockchain_provider(provider=MockParityProvider())


class GanacheClientTestInterface(BlockchainInterfaceTestBase):

    def _attach_blockchain_provider(self, *args, **kwargs) -> None:
        super()._attach_blockchain_provider(provider=MockGanacheProvider())


def test_client_no_provider():
    with pytest.raises(BlockchainInterface.NoProvider):
        interface = BlockchainInterfaceTestBase()
        interface.connect()


def test_geth_web3_client():
    interface = GethClientTestBlockchain(endpoint="file:///ipc.geth")
    interface.connect()

    assert isinstance(interface.client, GethClient)
    assert interface.client.node_technology == 'Geth'
    assert interface.client.node_version == 'v1.4.11-stable-fed692f6'
    assert interface.client.platform == 'darwin'
    assert interface.client.backend == 'go1.7'

    assert interface.client.is_local is False
    assert interface.client.chain_id == 5  # Hardcoded above


def test_autodetect_provider_type_file(tempfile_path):
    interface = ProviderTypeTestClient(
        endpoint=str(tempfile_path),  # existing file for test
        expected_provider_class=IPCProvider,
        actual_provider_to_attach=MockGethProvider(),
    )
    interface.connect()
    assert isinstance(interface.client, GethClient)


def test_autodetect_provider_type_file_none_existent():
    with pytest.raises(BlockchainInterface.UnsupportedProvider):
        interface = BlockchainInterfaceTestBase(endpoint="/none_existent.ipc.geth")
        interface.connect()


def test_detect_provider_type_file():
    interface = ProviderTypeTestClient(
        endpoint="file:///ipc.geth",
        expected_provider_class=IPCProvider,
        actual_provider_to_attach=MockGethProvider(),
    )
    interface.connect()
    assert isinstance(interface.client, GethClient)


def test_detect_provider_type_ipc():
    interface = ProviderTypeTestClient(
        endpoint="ipc:///ipc.geth",
        expected_provider_class=IPCProvider,
        actual_provider_to_attach=MockGethProvider(),
    )
    interface.connect()
    assert isinstance(interface.client, GethClient)


def test_detect_provider_type_http():
    interface = ProviderTypeTestClient(
        endpoint="http://ganache:8445",
        expected_provider_class=HTTPProvider,
        actual_provider_to_attach=MockGanacheProvider(),
    )
    interface.connect()
    assert isinstance(interface.client, GanacheClient)


def test_detect_provider_type_https():
    interface = ProviderTypeTestClient(
        endpoint="https://ganache:8445",
        expected_provider_class=HTTPProvider,
        actual_provider_to_attach=MockGanacheProvider(),
    )
    interface.connect()
    assert isinstance(interface.client, GanacheClient)


def test_detect_provider_type_ws():
    interface = ProviderTypeTestClient(
        endpoint=f"ws://{LOOPBACK_ADDRESS}:8546",
        expected_provider_class=WebsocketProvider,
        actual_provider_to_attach=MockWebSocketProvider(),
    )
    interface.connect()
    assert isinstance(interface.client, GethClient)


def test_infura_web3_client():
    interface = InfuraTestClient(
        endpoint="wss://:@goerli.infura.io/ws/v3/1234567890987654321abcdef"
    )
    interface.connect()

    assert isinstance(interface.client, InfuraClient)

    assert interface.client.node_technology == 'Geth'
    assert interface.client.node_version == 'v1.8.23-omnibus-2ad89aaa'
    assert interface.client.platform == 'linux-amd64'
    assert interface.client.backend == 'go1.11.1'
    assert interface.client.is_local is False
    assert interface.client.chain_id == 5

    assert interface.client.unlock_account('address', 'password')  # Returns True on success


def test_alchemy_web3_client():
    interface = AlchemyTestClient(
        endpoint="https://eth-rinkeby.alchemyapi.io/v2/1234567890987654321abcdef"
    )
    interface.connect()

    assert isinstance(interface.client, AlchemyClient)

    assert interface.client.node_technology == 'Geth'
    assert interface.client.node_version == 'v1.9.20-stable-979fc968'
    assert interface.client.platform == 'linux-amd64'
    assert interface.client.backend == 'go1.15'


def test_parity_web3_client():
    interface = ParityClientTestInterface(endpoint="file:///ipc.parity")
    interface.connect()

    assert isinstance(interface.client, ParityClient)
    assert interface.client.node_technology == 'Parity-Ethereum'
    assert interface.client.node_version == 'v2.5.1-beta-e0141f8-20190510'
    assert interface.client.platform == 'x86_64-linux-gnu'
    assert interface.client.backend == 'rustc1.34.1'


def test_ganache_web3_client():
    interface = GanacheClientTestInterface(endpoint="http://ganache:8445")
    interface.connect()

    assert isinstance(interface.client, GanacheClient)
    assert interface.client.node_technology == 'EthereumJS TestRPC'
    assert interface.client.node_version == 'v2.1.5'
    assert interface.client.platform is None
    assert interface.client.backend == 'ethereum-js'
    assert interface.client.is_local


def test_gas_prices(mocker, mock_ethereum_client):
    web3_mock = mock_ethereum_client.w3

    web3_mock.eth.generate_gas_price = mocker.Mock(side_effect=[None, GAS_PRICE_FROM_STRATEGY])
    type(web3_mock.eth).gas_price = PropertyMock(return_value=DEFAULT_GAS_PRICE)  # See docs of PropertyMock

    assert mock_ethereum_client.gas_price == DEFAULT_GAS_PRICE
    assert mock_ethereum_client.gas_price_for_transaction("there's no gas strategy") == DEFAULT_GAS_PRICE
    assert mock_ethereum_client.gas_price_for_transaction("2nd time is the charm") == GAS_PRICE_FROM_STRATEGY
