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

from unittest.mock import PropertyMock

import pytest
from web3 import HTTPProvider, IPCProvider, WebsocketProvider

from tests.mock.web3 import (
    MockGethProvider,
    MockParityProvider,
    MockGanacheProvider,
    MockInfuraProvider,
    MockAlchemyProvider,
    MockWebSocketProvider,
    MockWeb3
)
from nucypher.blockchain.eth.clients import (
    GanacheClient,
    GethClient,
    InfuraClient,
    PUBLIC_CHAINS,
    ParityClient,
    AlchemyClient
)
from nucypher.blockchain.eth.interfaces import BlockchainInterface
from tests.mock.web3 import GAS_PRICE_FROM_STRATEGY, DEFAULT_GAS_PRICE


class BlockchainInterfaceTestBase(BlockchainInterface):

    Web3 = MockWeb3

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

    def _attach_provider(self, *args, **kwargs) -> None:
        super()._attach_provider(*args, **kwargs)

        # check type
        assert isinstance(self.provider, self.expected_provider_class)

        super()._attach_provider(provider=self.test_provider_to_attach)


class InfuraTestClient(BlockchainInterfaceTestBase):

    def _attach_provider(self, *args, **kwargs) -> None:
        super()._attach_provider(provider=MockInfuraProvider())


class AlchemyTestClient(BlockchainInterfaceTestBase):

    def _attach_provider(self, *args, **kwargs) -> None:
        super()._attach_provider(provider=MockAlchemyProvider())


class GethClientTestBlockchain(BlockchainInterfaceTestBase):

    def _attach_provider(self, *args, **kwargs) -> None:
        super()._attach_provider(provider=MockGethProvider())

    @property
    def is_local(self):
        return int(self.w3.net.version) not in PUBLIC_CHAINS


class ParityClientTestInterface(BlockchainInterfaceTestBase):

    def _attach_provider(self, *args, **kwargs) -> None:
        super()._attach_provider(provider=MockParityProvider())


class GanacheClientTestInterface(BlockchainInterfaceTestBase):

    def _attach_provider(self, *args, **kwargs) -> None:
        super()._attach_provider(provider=MockGanacheProvider())


def test_client_no_provider():
    with pytest.raises(ValueError) as e:
        interface = BlockchainInterfaceTestBase()
        interface.connect()


def test_geth_web3_client():
    interface = GethClientTestBlockchain(provider_uri='ipc:///ipc.geth')
    interface.connect()

    assert isinstance(interface.client, GethClient)
    assert interface.client.node_technology == 'Geth'
    assert interface.client.node_version == 'v1.4.11-stable-fed692f6'
    assert interface.client.platform == 'darwin'
    assert interface.client.backend == 'go1.7'

    assert interface.client.is_local is False
    assert interface.client.chain_id == 123456789  # Hardcoded above


def test_autodetect_provider_type_file(tempfile_path):

    interface = ProviderTypeTestClient(provider_uri=tempfile_path,  # existing file for test
                                       expected_provider_class=IPCProvider,
                                       actual_provider_to_attach=MockGethProvider())
    interface.connect()
    assert isinstance(interface.client, GethClient)


def test_autodetect_provider_type_file_none_existent():
    with pytest.raises(BlockchainInterface.UnsupportedProvider) as e:
        interface = BlockchainInterfaceTestBase(provider_uri='/none_existent.ipc.geth')
        interface.connect()


def test_detect_provider_type_ipc():
    interface = ProviderTypeTestClient(provider_uri='ipc:///ipc.geth',
                                       expected_provider_class=IPCProvider,
                                       actual_provider_to_attach=MockGethProvider())
    interface.connect()
    assert isinstance(interface.client, GethClient)


def test_detect_provider_type_http():
    interface = ProviderTypeTestClient(provider_uri='http://ganache:8445',
                                       expected_provider_class=HTTPProvider,
                                       actual_provider_to_attach=MockGanacheProvider())
    interface.connect()
    assert isinstance(interface.client, GanacheClient)


def test_detect_provider_type_https():
    interface = ProviderTypeTestClient(provider_uri='https://ganache:8445',
                                       expected_provider_class=HTTPProvider,
                                       actual_provider_to_attach=MockGanacheProvider())
    interface.connect()
    assert isinstance(interface.client, GanacheClient)


def test_detect_provider_type_ws():
    interface = ProviderTypeTestClient(provider_uri='ws://127.0.0.1:8546',
                                       expected_provider_class=WebsocketProvider,
                                       actual_provider_to_attach=MockWebSocketProvider())
    interface.connect()
    assert isinstance(interface.client, GethClient)


def test_infura_web3_client():
    interface = InfuraTestClient(provider_uri='wss://:@goerli.infura.io/ws/v3/1234567890987654321abcdef')
    interface.connect()

    assert isinstance(interface.client, InfuraClient)

    assert interface.client.node_technology == 'Geth'
    assert interface.client.node_version == 'v1.8.23-omnibus-2ad89aaa'
    assert interface.client.platform == 'linux-amd64'
    assert interface.client.backend == 'go1.11.1'
    assert interface.client.is_local is False
    assert interface.client.chain_id == 123456789

    assert interface.client.unlock_account('address', 'password')  # Returns True on success


def test_alchemy_web3_client():
    interface = AlchemyTestClient(provider_uri='https://eth-rinkeby.alchemyapi.io/v2/1234567890987654321abcdef')
    interface.connect()

    assert isinstance(interface.client, AlchemyClient)

    assert interface.client.node_technology == 'Geth'
    assert interface.client.node_version == 'v1.9.20-stable-979fc968'
    assert interface.client.platform == 'linux-amd64'
    assert interface.client.backend == 'go1.15'


def test_parity_web3_client():
    interface = ParityClientTestInterface(provider_uri='file:///ipc.parity')
    interface.connect()

    assert isinstance(interface.client, ParityClient)
    assert interface.client.node_technology == 'Parity-Ethereum'
    assert interface.client.node_version == 'v2.5.1-beta-e0141f8-20190510'
    assert interface.client.platform == 'x86_64-linux-gnu'
    assert interface.client.backend == 'rustc1.34.1'


def test_ganache_web3_client():
    interface = GanacheClientTestInterface(provider_uri='http://ganache:8445')
    interface.connect()

    assert isinstance(interface.client, GanacheClient)
    assert interface.client.node_technology == 'EthereumJS TestRPC'
    assert interface.client.node_version == 'v2.1.5'
    assert interface.client.platform is None
    assert interface.client.backend == 'ethereum-js'
    assert interface.client.is_local


def test_gas_prices(mocker, mock_ethereum_client):
    web3_mock = mock_ethereum_client.w3

    web3_mock.eth.generateGasPrice = mocker.Mock(side_effect=[None, GAS_PRICE_FROM_STRATEGY])
    type(web3_mock.eth).gasPrice = PropertyMock(return_value=DEFAULT_GAS_PRICE)  # See docs of PropertyMock

    assert mock_ethereum_client.gas_price == DEFAULT_GAS_PRICE
    assert mock_ethereum_client.gas_price_for_transaction("there's no gas strategy") == DEFAULT_GAS_PRICE
    assert mock_ethereum_client.gas_price_for_transaction("2nd time is the charm") == GAS_PRICE_FROM_STRATEGY
