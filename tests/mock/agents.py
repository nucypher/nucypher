from unittest.mock import Mock

from hexbytes.main import HexBytes

from nucypher.blockchain.eth.agents import WorkLockAgent
from nucypher.blockchain.eth.interfaces import BlockchainInterfaceFactory
from nucypher.utilities.sandbox.constants import MOCK_PROVIDER_URI

mock_testerchain = BlockchainInterfaceFactory.get_or_create_interface(provider_uri=MOCK_PROVIDER_URI)
blocktime = mock_testerchain.w3.eth.getBlock(block_identifier='latest')
now = blocktime.timestamp
current_block = blocktime.number

# Fixtures
FAKE_RECEIPT = {'transactionHash': HexBytes(b'FAKE29890FAKE8349804'),
                'gasUsed': 1,
                'blockNumber': current_block,
                'blockHash': HexBytes(b'FAKE43434343FAKE43443434')}


class MockContractAgent:

    blockchain = mock_testerchain

    def __init__(self): pass

    def __getattribute__(self, item):
        try:
            return object.__getattribute__(MockWorkLockAgent, item)
        except AttributeError:
            from typing import get_type_hints
            try:
                attr = object.__getattribute__(self, item)
            except AttributeError:
                attr = Mock()
            return attr


class MockWorkLockAgent(MockContractAgent, WorkLockAgent):

    # Attributes
    start_bidding_date = now - 10
    end_bidding_date = now + 10
    minimum_allowed_bid = 1  # token_economics.worklock_min_allowed_bid

    # Transactions
    transactions = ('bid',
                    'cancel_bid',
                    'force_refund',
                    'verify_bidding_correctness',
                    'claim',
                    'refund',
                    'withdraw_compensation')

    # Calls
    eth_to_tokens = lambda *args, **kwargs: 1
    get_deposited_eth = lambda *args, **kwargs: 1

    def __init__(self):
        for t in self.transactions:
            setattr(MockWorkLockAgent, t, lambda *args, **kwargs: FAKE_RECEIPT)


