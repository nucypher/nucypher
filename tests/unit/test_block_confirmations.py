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
import time
from unittest.mock import PropertyMock

import pytest
from hexbytes import HexBytes
from web3.exceptions import TransactionNotFound, TimeExhausted

from tests.mock.interfaces import MockEthereumClient


@pytest.fixture()
def receipt():
    block_number_of_my_tx = 42
    my_tx_hash = HexBytes('0xFabadaAcabada')
    receipt = {
        'transactionHash': my_tx_hash,
        'blockNumber': block_number_of_my_tx,
        'blockHash': HexBytes('0xBebeCafe')
    }
    return receipt


def test_check_transaction_is_on_chain(mocker, mock_ethereum_client, receipt):
    # Mocking Web3 and EthereumClient
    web3_mock = mock_ethereum_client.w3
    web3_mock.eth.getTransactionReceipt = mocker.Mock(return_value=receipt)

    # Test with no chain reorganizations:

    # While web3 keeps returning the same receipt that we initially had, all good
    assert mock_ethereum_client.check_transaction_is_on_chain(receipt=receipt)

    # Test with chain re-organizations:

    # Let's assume that our TX ends up mined in a different block, and we receive a new receipt
    new_receipt = dict(receipt)
    new_receipt.update({'blockHash': HexBytes('0xBebeCebada')})

    web3_mock.eth.getTransactionReceipt = mocker.Mock(return_value=new_receipt)

    exception = mock_ethereum_client.ChainReorganizationDetected
    message = exception(receipt=receipt).message
    with pytest.raises(exception, match=message):
        _ = mock_ethereum_client.check_transaction_is_on_chain(receipt=receipt)

    # Another example: there has been a chain reorganization and our beloved TX is gone for good:
    web3_mock.eth.getTransactionReceipt = mocker.Mock(side_effect=TransactionNotFound)
    with pytest.raises(exception, match=message):
        _ = mock_ethereum_client.check_transaction_is_on_chain(receipt=receipt)


def test_block_until_enough_confirmations(mocker, mock_ethereum_client, receipt):
    my_tx_hash = receipt['transactionHash']
    block_number_of_my_tx = receipt['blockNumber']

    # Test that web3's TimeExhausted is propagated:
    web3_mock = mock_ethereum_client.w3
    web3_mock.eth.waitForTransactionReceipt = mocker.Mock(side_effect=TimeExhausted)

    with pytest.raises(TimeExhausted):
        mock_ethereum_client.block_until_enough_confirmations(transaction_hash=my_tx_hash,
                                                              timeout=1,
                                                              confirmations=1)

    # Test that NotEnoughConfirmations is raised when there are not enough confirmations.
    # In this case, we're going to mock eth.blockNumber to be stuck
    web3_mock.eth.waitForTransactionReceipt = mocker.Mock(return_value=receipt)
    web3_mock.eth.getTransactionReceipt = mocker.Mock(return_value=receipt)

    type(web3_mock.eth).blockNumber = PropertyMock(return_value=block_number_of_my_tx)  # See docs of PropertyMock

    # Additional adjustments to make the test faster
    mocker.patch.object(mock_ethereum_client, '_calculate_confirmations_timeout', return_value=0.1)
    mock_ethereum_client.BLOCK_CONFIRMATIONS_POLLING_TIME = 0

    with pytest.raises(mock_ethereum_client.NotEnoughConfirmations):
        mock_ethereum_client.block_until_enough_confirmations(transaction_hash=my_tx_hash,
                                                              timeout=1,
                                                              confirmations=1)

    # Test that block_until_enough_confirmations keeps iterating until the required confirmations are obtained
    required_confirmations = 3
    new_blocks_sequence = range(block_number_of_my_tx, block_number_of_my_tx + required_confirmations + 1)
    type(web3_mock.eth).blockNumber = PropertyMock(side_effect=new_blocks_sequence)  # See docs of PropertyMock
    spy_check_transaction = mocker.spy(mock_ethereum_client, 'check_transaction_is_on_chain')

    returned_receipt = mock_ethereum_client.block_until_enough_confirmations(transaction_hash=my_tx_hash,
                                                                             timeout=1,
                                                                             confirmations=required_confirmations)
    assert receipt == returned_receipt
    assert required_confirmations + 1 == spy_check_transaction.call_count


def test_wait_for_receipt_no_confirmations(mocker, mock_ethereum_client, receipt):
    my_tx_hash = receipt['transactionHash']

    # Test that web3's TimeExhausted is propagated:
    web3_mock = mock_ethereum_client.w3
    web3_mock.eth.waitForTransactionReceipt = mocker.Mock(side_effect=TimeExhausted)
    with pytest.raises(TimeExhausted):
        _ = mock_ethereum_client.wait_for_receipt(transaction_hash=my_tx_hash, timeout=1, confirmations=0)
    web3_mock.eth.waitForTransactionReceipt.assert_called_once_with(transaction_hash=my_tx_hash,
                                                                    timeout=1,
                                                                    poll_latency=MockEthereumClient.TRANSACTION_POLLING_TIME)

    # Test that when web3's layer returns the receipt, we get that receipt
    web3_mock.eth.waitForTransactionReceipt = mocker.Mock(return_value=receipt)
    returned_receipt = mock_ethereum_client.wait_for_receipt(transaction_hash=my_tx_hash, timeout=1, confirmations=0)
    assert receipt == returned_receipt
    web3_mock.eth.waitForTransactionReceipt.assert_called_once_with(transaction_hash=my_tx_hash,
                                                                    timeout=1,
                                                                    poll_latency=MockEthereumClient.TRANSACTION_POLLING_TIME)


def test_wait_for_receipt_with_confirmations(mocker, mock_ethereum_client, receipt):
    my_tx_hash = receipt['transactionHash']

    mock_ethereum_client.COOLING_TIME = 0  # Don't make test unnecessarily slow

    time_spy = mocker.spy(time, 'sleep')
    # timeout_spy = mocker.spy(Timeout, 'check')  # FIXME

    # First, let's make a simple, successful call to check that:
    #   - The same receipt goes through
    #   - The cooling time is respected
    mock_ethereum_client.block_until_enough_confirmations = mocker.Mock(return_value=receipt)
    returned_receipt = mock_ethereum_client.wait_for_receipt(transaction_hash=my_tx_hash, timeout=1, confirmations=1)
    assert receipt == returned_receipt
    time_spy.assert_called_once_with(mock_ethereum_client.COOLING_TIME)
    # timeout_spy.assert_not_called()  # FIXME

    # Test that wait_for_receipt finishes when a receipt is returned by block_until_enough_confirmations
    sequence_of_events = (
        TimeExhausted,
        mock_ethereum_client.ChainReorganizationDetected(receipt),
        mock_ethereum_client.NotEnoughConfirmations,
        receipt
    )
    timeout = None

    mock_ethereum_client.BLOCK_CONFIRMATIONS_POLLING_TIME = 0
    mock_ethereum_client.block_until_enough_confirmations = mocker.Mock(side_effect=sequence_of_events)

    returned_receipt = mock_ethereum_client.wait_for_receipt(transaction_hash=my_tx_hash, timeout=timeout, confirmations=1)
    assert receipt == returned_receipt
    # assert timeout_spy.call_count == 3  # FIXME

    # Test that a TransactionTimeout is thrown when no receipt is found during the given time
    timeout = 0.1
    sequence_of_events = [TimeExhausted] * 10
    mock_ethereum_client.BLOCK_CONFIRMATIONS_POLLING_TIME = 0.015
    mock_ethereum_client.block_until_enough_confirmations = mocker.Mock(side_effect=sequence_of_events)
    with pytest.raises(mock_ethereum_client.TransactionTimeout):
        _ = mock_ethereum_client.wait_for_receipt(transaction_hash=my_tx_hash,
                                                  timeout=timeout,
                                                  confirmations=1)
