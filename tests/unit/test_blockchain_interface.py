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
from web3.gas_strategies import time_based

from constant_sorrow.constants import ALL_OF_THEM

from nucypher.blockchain.eth.interfaces import BlockchainInterface
from nucypher.utilities.gas_strategies import WEB3_GAS_STRATEGIES
from tests.mock.interfaces import MockBlockchain


@pytest.fixture(scope='module')
def mock_testerchain(_mock_testerchain) -> MockBlockchain:
    testerchain = _mock_testerchain
    yield testerchain


def test_get_gas_strategy():

    # Testing Web3's bundled time-based gas strategies
    for gas_strategy_name, expected_gas_strategy in WEB3_GAS_STRATEGIES.items():
        gas_strategy = BlockchainInterface.get_gas_strategy(gas_strategy_name)
        assert expected_gas_strategy == gas_strategy
        assert callable(gas_strategy)

    # Passing a callable gas strategy
    callable_gas_strategy = time_based.glacial_gas_price_strategy
    assert callable_gas_strategy == BlockchainInterface.get_gas_strategy(callable_gas_strategy)

    # Passing None should retrieve the default gas strategy
    assert BlockchainInterface.DEFAULT_GAS_STRATEGY == 'fast'
    default = WEB3_GAS_STRATEGIES[BlockchainInterface.DEFAULT_GAS_STRATEGY]
    gas_strategy = BlockchainInterface.get_gas_strategy()
    assert default == gas_strategy


def test_use_pending_nonce_when_building_payload(mock_testerchain, mocker):
    sender = mock_testerchain.unassigned_accounts[0]

    # Mock transaction count retrieval
    transaction_count = dict(latest=0, pending=0)

    def mock_get_transaction_count(sender, block_identifier) -> int:
        return transaction_count[block_identifier]

    mock_testerchain.client.w3.eth.getTransactionCount = mocker.Mock(side_effect=mock_get_transaction_count)

    def simulate_successful_transaction():
        transaction_count['pending'] += 1
        transaction_count['latest'] = transaction_count['pending']

    def simulate_pending_transaction():
        transaction_count['pending'] += 1

    def simulate_clearing_transactions(how_many: int = ALL_OF_THEM):
        if how_many == ALL_OF_THEM:
            transaction_count['latest'] = transaction_count['pending']
        else:
            transaction_count['latest'] += how_many

    # Initially, the transaction count is 0, so the computed nonce is 0 in both modes
    payload = mock_testerchain.build_payload(sender_address=sender, payload=None, use_pending_nonce=True)
    assert payload['nonce'] == 0
    payload = mock_testerchain.build_payload(sender_address=sender, payload=None, use_pending_nonce=False)
    assert payload['nonce'] == 0

    # Let's assume we have a successful TX, so next payload should get nonce == 1
    simulate_successful_transaction()

    payload = mock_testerchain.build_payload(sender_address=sender, payload=None)
    assert payload['nonce'] == 1

    # Let's assume next TX has a low price and when we query the TX count, it's pending.
    simulate_pending_transaction()

    # Default behavior gets the TX count including pending, so nonce should be 2
    payload = mock_testerchain.build_payload(sender_address=sender, payload=None)
    assert payload['nonce'] == 2

    # But if we ignore pending, nonce should still be 1
    payload = mock_testerchain.build_payload(sender_address=sender, payload=None, use_pending_nonce=False)
    assert payload['nonce'] == 1

    # Let's fire some pending TXs
    simulate_pending_transaction()
    simulate_pending_transaction()
    simulate_pending_transaction()
    simulate_pending_transaction()

    payload = mock_testerchain.build_payload(sender_address=sender, payload=None, use_pending_nonce=True)
    assert payload['nonce'] == 6
    payload = mock_testerchain.build_payload(sender_address=sender, payload=None, use_pending_nonce=False)
    assert payload['nonce'] == 1

    # One of them gets mined ...
    simulate_clearing_transactions(how_many=1)

    payload = mock_testerchain.build_payload(sender_address=sender, payload=None, use_pending_nonce=True)
    assert payload['nonce'] == 6
    payload = mock_testerchain.build_payload(sender_address=sender, payload=None, use_pending_nonce=False)
    assert payload['nonce'] == 2

    # If all TXs clear up, then nonce should be 6 in both modes
    simulate_clearing_transactions(how_many=ALL_OF_THEM)

    payload = mock_testerchain.build_payload(sender_address=sender, payload=None, use_pending_nonce=True)
    assert payload['nonce'] == 6
    payload = mock_testerchain.build_payload(sender_address=sender, payload=None, use_pending_nonce=False)
    assert payload['nonce'] == 6
