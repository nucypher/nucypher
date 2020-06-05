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

import pytest
from hexbytes import HexBytes
from web3.exceptions import TransactionNotFound

from tests.mock.interfaces import MockEthereumClient


@pytest.fixture(scope='function')
def mock_ethereum_client(mocker):
    web3_mock = mocker.Mock()
    mock_client = MockEthereumClient(w3=web3_mock)
    return mock_client


def test_check_transaction_is_on_chain(mocker, mock_ethereum_client):

    # Mock data
    block_number_of_my_tx = 42
    my_tx_hash = HexBytes('0xFabadaAcabada')

    receipt = {
        'transactionHash': my_tx_hash,
        'blockNumber': block_number_of_my_tx,
        'blockHash': HexBytes('0xBebeCafe')
    }

    # Mocking Web3 and EthereumClient
    web3_mock = mock_ethereum_client.w3
    web3_mock.eth.getTransactionReceipt = mocker.Mock(return_value=receipt)

    # Test with no chain reorganizations:

    # While web3 keeps returning the same receipt that we initially had, all good
    assert mock_ethereum_client.check_transaction_is_on_chain(receipt=receipt)

    # Test with chain re-organizations:

    # Let's assume that our TX ends up mined in a different block, and we receive a new receipt
    new_receipt = {
        'transactionHash': my_tx_hash,
        'blockNumber': block_number_of_my_tx,
        'blockHash': HexBytes('0xBebeCebada')
    }
    web3_mock.eth.getTransactionReceipt = mocker.Mock(return_value=new_receipt)

    exception = mock_ethereum_client.ChainReorganizationDetected
    message = exception(receipt=receipt).message
    with pytest.raises(exception, match=message):
        _ = mock_ethereum_client.check_transaction_is_on_chain(receipt=receipt)

    # Another example: there has been a chain reorganization and our beloved TX is gone for good:
    web3_mock.eth.getTransactionReceipt = mocker.Mock(side_effect=TransactionNotFound)
    with pytest.raises(exception, match=message):
        _ = mock_ethereum_client.check_transaction_is_on_chain(receipt=receipt)
