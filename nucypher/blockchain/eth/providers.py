from typing import Union

from eth_tester import EthereumTester, PyEVMBackend
from eth_tester.backends.mock.main import MockBackend
from web3 import HTTPProvider
from web3.providers import BaseProvider
from web3.providers.eth_tester.main import EthereumTesterProvider

from nucypher.exceptions import DevelopmentInstallationRequired


def _get_http_provider(endpoint) -> BaseProvider:
    from nucypher.blockchain.eth.interfaces import BlockchainInterface

    return HTTPProvider(
        endpoint_uri=endpoint,
        request_kwargs={"timeout": BlockchainInterface.TIMEOUT},
    )


def _get_pyevm_test_backend() -> PyEVMBackend:
    try:
        # TODO: Consider packaged support of --dev mode with testerchain
        from tests.constants import PYEVM_GAS_LIMIT
    except ImportError:
        raise DevelopmentInstallationRequired(importable_name='tests.constants')

    genesis_params = PyEVMBackend._generate_genesis_params(overrides={'gas_limit': PYEVM_GAS_LIMIT})
    pyevm_backend = PyEVMBackend(genesis_parameters=genesis_params)
    pyevm_backend.reset_to_genesis(genesis_params=genesis_params, num_accounts=10)
    return pyevm_backend


def _get_ethereum_tester(test_backend: Union[PyEVMBackend, MockBackend]) -> EthereumTesterProvider:
    eth_tester = EthereumTester(backend=test_backend, auto_mine_transactions=True)
    provider = EthereumTesterProvider(ethereum_tester=eth_tester)
    return provider


def _get_pyevm_test_provider(endpoint) -> BaseProvider:
    """ Test provider entry-point"""
    # https://github.com/ethereum/eth-tester#pyevm-experimental
    pyevm_eth_tester = _get_pyevm_test_backend()
    provider = _get_ethereum_tester(test_backend=pyevm_eth_tester)
    return provider


def _get_mock_test_provider(endpoint) -> BaseProvider:
    # https://github.com/ethereum/eth-tester#mockbackend
    mock_backend = MockBackend()
    provider = _get_ethereum_tester(test_backend=mock_backend)
    return provider
