from typing import Optional
from unittest.mock import PropertyMock

from constant_sorrow.constants import ALL_OF_THEM
from requests import HTTPError
from web3 import BaseProvider
from web3.gas_strategies import time_based

from nucypher.blockchain.eth.interfaces import BlockchainInterface
from nucypher.utilities.gas_strategies import WEB3_GAS_STRATEGIES


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


def test_use_pending_nonce_when_building_payload(mock_testerchain, mocker, random_address):
    sender = random_address

    # Mock transaction count retrieval
    transaction_count = dict(latest=0, pending=0)

    def mock_get_transaction_count(sender, block_identifier) -> int:
        return transaction_count[block_identifier]

    mock_testerchain.client.w3.eth.get_transaction_count = mocker.Mock(side_effect=mock_get_transaction_count)

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


def test_connect_handle_connectivity_issues(mocker):

    mock_eth = mocker.MagicMock()
    type(mock_eth).chain_id = PropertyMock(return_value=137)

    mock_middleware_onion = mocker.Mock()

    class MockWeb3:
        def __init__(self, provider: Optional[BaseProvider] = None, *args, **kwargs):
            self.provider = provider
            self.eth = mock_eth
            self.middleware_onion = mock_middleware_onion

            middlewares = []
            self.middleware_onion.middlewares = middlewares

            def add_middleware(middleware, name=None):
                middlewares.append(middleware)

            def inject_middleware(middleware, layer=0, name=None):
                middlewares.insert(layer, middleware)

            mock_middleware_onion.add.side_effect = add_middleware
            mock_middleware_onion.inject.side_effect = inject_middleware

    class TestBlockchainInterface(BlockchainInterface):
        Web3 = MockWeb3

    blockchain_interface = TestBlockchainInterface(
        endpoint="https://public-node.io:8445"
    )

    assert not blockchain_interface.is_initialized

    # connect() is called with no connectivity issues and executes successfully
    blockchain_interface.connect()
    assert blockchain_interface.is_initialized

    # poa, retry, simplecache
    current_middlewares = blockchain_interface.w3.middleware_onion.middlewares
    assert len(current_middlewares) == 3

    w3 = blockchain_interface.w3
    client = blockchain_interface.client
    tx_machine = blockchain_interface.tx_machine

    # mimic connectivity issues
    type(mock_eth).chain_id = PropertyMock(side_effect=HTTPError("connectivity issue"))

    # Mimic scanner task that connectivity experienced exception and ran connect()
    # again on blockchain interface.
    # However, connect() does nothing the 2nd time around because it already completed
    # successfully the first time
    blockchain_interface.connect()

    # no change;
    # same underlying instances
    assert w3 == blockchain_interface.w3
    assert client == blockchain_interface.client
    assert tx_machine == blockchain_interface.tx_machine

    # same middlewares remain - poa, retry, simplecache
    assert len(blockchain_interface.w3.middleware_onion.middlewares) == 3
    assert blockchain_interface.w3.middleware_onion.middlewares == current_middlewares
