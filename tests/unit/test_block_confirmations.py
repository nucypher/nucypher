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
from hexbytes import HexBytes

from nucypher.blockchain.eth.clients import EthereumClient
from tests.mock.interfaces import MockEthereumClient


@pytest.fixture(scope='function')
def mock_ethereum_client(mocker):
    web3_mock = mocker.Mock()
    mock_client = MockEthereumClient(w3=web3_mock)
    return mock_client


def test_get_confirmations(mocker, mock_ethereum_client):

    # Mock data
    block_number_of_my_tx = 42
    my_tx_hash = HexBytes('0xFabadaAcabada')

    receipt = {
        'transactionHash': my_tx_hash,
        'blockNumber': block_number_of_my_tx,
        'blockHash': HexBytes('0xBebeCafe')
    }

    our_block = {
        'number': block_number_of_my_tx,
        'transactions': [my_tx_hash],
        'blockHash': HexBytes('0xBebeCafe')
    }

    the_blockchain = {
        block_number_of_my_tx: our_block
    }

    # Mocking Web3 and EthereumClient
    def mock_web3_get_block(block_identifier, full_transactions=False):
        return the_blockchain[block_identifier]

    def mock_web3_get_block_number():
        return list(sorted(the_blockchain.keys()))[-1]

    web3_mock = mock_ethereum_client.w3
    web3_mock.eth.getBlock = mocker.Mock(side_effect=mock_web3_get_block)
    type(web3_mock.eth).blockNumber = PropertyMock(side_effect=mock_web3_get_block_number)  # See docs of PropertyMock

    # Test with no chain reorganizations
    for additional_blocks in range(10):
        obtained_confirmations = mock_ethereum_client.get_confirmations(receipt=receipt)
        assert additional_blocks == obtained_confirmations

        # Mine a new block in this fine chain of ours
        next_block_number = block_number_of_my_tx + additional_blocks + 1
        mined_block = {'number': next_block_number, 'transactions': []}
        the_blockchain[next_block_number] = mined_block

    # Wow, there has been a chain reorganization and our beloved TX is gone:
    we_hate_this_block = {'number': block_number_of_my_tx,
                          'transactions': [HexBytes('0xDefeca')],
                          'blockHash': HexBytes('0xCaca')}
    the_blockchain = {
        block_number_of_my_tx: we_hate_this_block
    }

    exception = mock_ethereum_client.ChainReorganizationDetected
    message = exception(receipt=receipt, block=we_hate_this_block).message
    with pytest.raises(exception, match=message):
        _ = mock_ethereum_client.get_confirmations(receipt=receipt)
