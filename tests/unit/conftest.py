

import pytest

from tests.mock.interfaces import MockEthereumClient


@pytest.fixture(scope='function')
def mock_ethereum_client(mocker):
    web3_mock = mocker.Mock()
    mock_client = MockEthereumClient(w3=web3_mock)
    return mock_client
