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


from eth_tester import EthereumTester, PyEVMBackend
from eth_tester.backends.mock.main import MockBackend
from typing import Union
from urllib.parse import urlparse
from web3 import HTTPProvider, IPCProvider, WebsocketProvider
from web3.providers import BaseProvider
from web3.providers.eth_tester.main import EthereumTesterProvider

from nucypher.exceptions import DevelopmentInstallationRequired


class ProviderError(Exception):
    pass


def _get_IPC_provider(provider_uri) -> BaseProvider:
    uri_breakdown = urlparse(provider_uri)
    from nucypher.blockchain.eth.interfaces import BlockchainInterface
    return IPCProvider(ipc_path=uri_breakdown.path,
                       timeout=BlockchainInterface.TIMEOUT,
                       request_kwargs={'timeout': BlockchainInterface.TIMEOUT})


def _get_HTTP_provider(provider_uri) -> BaseProvider:
    from nucypher.blockchain.eth.interfaces import BlockchainInterface
    return HTTPProvider(endpoint_uri=provider_uri, request_kwargs={'timeout': BlockchainInterface.TIMEOUT})


def _get_websocket_provider(provider_uri) -> BaseProvider:
    from nucypher.blockchain.eth.interfaces import BlockchainInterface
    return WebsocketProvider(endpoint_uri=provider_uri, websocket_kwargs={'timeout': BlockchainInterface.TIMEOUT})


def _get_auto_provider(provider_uri) -> BaseProvider:
    from web3.auto import w3
    # how-automated-detection-works: https://web3py.readthedocs.io/en/latest/providers.html
    connected = w3.isConnected()
    if not connected:
        raise ProviderError('Cannot auto-detect node.  Provide a full URI instead.')
    return w3.provider


def _get_pyevm_test_backend() -> PyEVMBackend:
    try:
        # TODO: Consider packaged support of --dev mode with testerchain
        from tests.constants import PYEVM_GAS_LIMIT, NUMBER_OF_ETH_TEST_ACCOUNTS
    except ImportError:
        raise DevelopmentInstallationRequired(importable_name='tests.constants')

    # Initialize
    genesis_params = PyEVMBackend._generate_genesis_params(overrides={'gas_limit': PYEVM_GAS_LIMIT})
    pyevm_backend = PyEVMBackend(genesis_parameters=genesis_params)
    pyevm_backend.reset_to_genesis(genesis_params=genesis_params, num_accounts=NUMBER_OF_ETH_TEST_ACCOUNTS)
    return pyevm_backend


def _get_ethereum_tester(test_backend: Union[PyEVMBackend, MockBackend]) -> EthereumTesterProvider:
    eth_tester = EthereumTester(backend=test_backend, auto_mine_transactions=True)
    provider = EthereumTesterProvider(ethereum_tester=eth_tester)
    return provider


def _get_pyevm_test_provider(provider_uri) -> BaseProvider:
    """ Test provider entry-point"""
    # https://github.com/ethereum/eth-tester#pyevm-experimental
    pyevm_eth_tester = _get_pyevm_test_backend()
    provider = _get_ethereum_tester(test_backend=pyevm_eth_tester)
    return provider


def _get_mock_test_provider(provider_uri) -> BaseProvider:
    # https://github.com/ethereum/eth-tester#mockbackend
    mock_backend = MockBackend()
    provider = _get_ethereum_tester(test_backend=mock_backend)
    return provider


def _get_tester_ganache(provider_uri=None) -> BaseProvider:
    endpoint_uri = provider_uri or 'http://localhost:7545'
    return HTTPProvider(endpoint_uri=endpoint_uri)
