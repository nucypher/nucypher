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

from unittest.mock import Mock

import datetime

from web3.datastructures import AttributeDict

DEFAULT_GAS_PRICE = 42
GAS_PRICE_FROM_STRATEGY = 1234


class MockGethProvider:
    endpoint_uri = 'file:///ipc.geth'
    clientVersion = 'Geth/v1.4.11-stable-fed692f6/darwin/go1.7'


class MockParityProvider:
    endpoint_uri = 'file:///ipc.parity'
    clientVersion = 'Parity-Ethereum/v2.5.1-beta-e0141f8-20190510/x86_64-linux-gnu/rustc1.34.1'


class MockGanacheProvider:
    endpoint_uri = 'http://ganache:8445'
    clientVersion = 'EthereumJS TestRPC/v2.1.5/ethereum-js'


class MockInfuraProvider:
    endpoint_uri = 'wss://:@goerli.infura.io/ws/v3/1234567890987654321abcdef'
    clientVersion = 'Geth/v1.8.23-omnibus-2ad89aaa/linux-amd64/go1.11.1'


class MockAlchemyProvider:
    endpoint_uri = 'https://eth-rinkeby.alchemyapi.io/v2/1234567890987654321abcdef'
    clientVersion = 'Geth/v1.9.20-stable-979fc968/linux-amd64/go1.15'


class MockWebSocketProvider:
    endpoint_uri = 'ws://127.0.0.1:8546'
    clientVersion = 'Geth/v1.8.23-omnibus-2ad89aaa/linux-amd64/go1.11.1'


class MockW3Eth:

    version = 5
    chainId = 123456789
    blockNumber = 5

    gas_strategy = None

    def getBlock(self, block_identifier):
        return AttributeDict({
            'timestamp': datetime.datetime.timestamp(datetime.datetime.now() - datetime.timedelta(seconds=20))
        })

    def setGasPriceStrategy(self, gas_strategy):
        self.gas_strategy = True

    def generateGasPrice(self, transaction):
        if self.gas_strategy:
            return GAS_PRICE_FROM_STRATEGY
        else:
            return DEFAULT_GAS_PRICE

    def getBalance(self, account):
        return 1_000_000_000


class MockedW3GethWithPeers:

    @property
    def admin(self):
        class GethAdmin:
            def peers(self):
                return [1, 2, 3]
        return GethAdmin()


class MockWeb3:

    net = MockW3Eth()
    eth = MockW3Eth()
    geth = MockedW3GethWithPeers()

    def __init__(self, provider=None):
        self.provider = provider
        self.middleware_onion = Mock()

    @property
    def clientVersion(self):
        return self.provider.clientVersion

    @property
    def isConnected(self):
        return lambda: True
