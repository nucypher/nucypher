from unittest.mock import Mock

from hexbytes.main import HexBytes

from nucypher.blockchain.eth.agents import WorkLockAgent, StakingEscrowAgent
from nucypher.blockchain.eth.constants import NULL_ADDRESS
from nucypher.blockchain.eth.interfaces import BlockchainInterfaceFactory
from nucypher.utilities.sandbox.constants import MOCK_PROVIDER_URI

mock_testerchain = BlockchainInterfaceFactory.get_or_create_interface(provider_uri=MOCK_PROVIDER_URI)
blocktime = mock_testerchain.w3.eth.getBlock(block_identifier='latest')
now = blocktime.timestamp
current_block = blocktime.number

#
# Fixtures
#

FAKE_RECEIPT = {'transactionHash': HexBytes(b'FAKE29890FAKE8349804'),
                'gasUsed': 1,
                'blockNumber': current_block,
                'blockHash': HexBytes(b'FAKE43434343FAKE43443434')}


def fake_transaction(*_a, **_kw) -> dict:
    return FAKE_RECEIPT


def fake_call(*_a, **_kw) -> 1:
    return 1


#
# Agents
#

class MockContractAgent:

    registry = Mock()
    blockchain = mock_testerchain

    contract = Mock()
    contract_address = NULL_ADDRESS

    TRANSACTIONS = NotImplemented
    CALLS = NotImplemented

    def __init__(self):
        self.setup_mock()

    @classmethod
    def setup_mock(cls):
        for tx in cls.TRANSACTIONS:
            setattr(cls, tx, fake_transaction)
        for call in cls.CALLS:
            setattr(cls, call, fake_call)


class MockStakingAgent(MockContractAgent, StakingEscrowAgent):

    get_completed_work = 1


class MockWorkLockAgent(MockContractAgent, WorkLockAgent):

    #
    # Mock Worklock Attributes
    #

    # Time
    start_bidding_date = now - 10
    end_bidding_date = now + 10
    end_cancellation_date = end_bidding_date + 1

    # Contribution
    minimum_allowed_bid = 1  # token_economics.worklock_min_allowed_bid

    # Rate
    boosting_refund = 1
    slowing_refund = 1
    lot_value = 1

    CALLS = ('check_claim',
             'eth_to_tokens',
             'get_deposited_eth',
             'get_eth_supply',
             'get_base_deposit_rate',
             'get_bonus_lot_value',
             'get_bonus_deposit_rate',
             'get_bonus_refund_rate',
             'get_base_refund_rate',
             'get_completed_work',
             'get_refunded_work')

    TRANSACTIONS = ('bid',
                    'cancel_bid',
                    'force_refund',
                    'verify_bidding_correctness',
                    'claim',
                    'refund',
                    'withdraw_compensation')
