from collections import defaultdict
from typing import Tuple

from functools import partial

from hexbytes import HexBytes
from unittest.mock import Mock

from nucypher.blockchain.economics import EconomicsFactory
from nucypher.blockchain.eth.agents import WorkLockAgent, StakingEscrowAgent
from nucypher.blockchain.eth.constants import NULL_ADDRESS
from nucypher.blockchain.eth.interfaces import BlockchainInterfaceFactory
from nucypher.utilities.sandbox.constants import MOCK_PROVIDER_URI

MOCK_TESTERCHAIN = BlockchainInterfaceFactory.get_or_create_interface(provider_uri=MOCK_PROVIDER_URI)
CURRENT_BLOCK = MOCK_TESTERCHAIN.w3.eth.getBlock(block_identifier='latest')

#
# Fixtures
#

FAKE_RECEIPT = {'transactionHash': HexBytes(b'FAKE29890FAKE8349804'),
                'gasUsed': 1,
                'blockNumber': CURRENT_BLOCK.number,
                'blockHash': HexBytes(b'FAKE43434343FAKE43443434')}


def fake_transaction(*_a, **_kw) -> dict:
    return FAKE_RECEIPT


def fake_call(*_a, **_kw) -> 1:
    return 1


#
# Agents
#


class MockContractAgent:

    # Internal
    registry = Mock()
    blockchain = MOCK_TESTERCHAIN

    contract = Mock()
    contract_address = NULL_ADDRESS

    # API
    ATTRS = dict()
    CALLS = tuple()
    TRANSACTIONS = tuple()

    # Spy
    _SPY_TRANSACTIONS = defaultdict(list)
    _SPY_CALLS = defaultdict(list)

    def __init__(self):

        # Bind mock agent attributes to the *subclass*
        for agent_method, mock_value in self.ATTRS.items():
            setattr(self.__class__, agent_method, mock_value)
        self.setup_mock()

    def __record_tx(self, name: str, params: tuple):
        self._SPY_TRANSACTIONS[str(name)].append(params)

    def __record_call(self, name: str, params: tuple):
        self._SPY_CALLS[str(name)].append(params)

    def __getattribute__(self, name):
        """Spy"""
        get = object.__getattribute__
        attr = get(self, name)
        transaction = name in get(self, 'TRANSACTIONS')
        call = name in get(self, 'CALLS')

        if transaction or call:
            spy = self.__record_tx if transaction else self.__record_call
            def wrapped(*args, **kwargs):
                result = attr(*args, **kwargs)
                params = args, kwargs
                spy(name, params)
                return result
            return wrapped
        else:
            return attr

    @classmethod
    def setup_mock(cls):
        for call in cls.CALLS:
            setattr(cls, call, fake_call)
        for tx in cls.TRANSACTIONS:
            setattr(cls, tx, fake_transaction)

    #
    # Assertions
    #

    def assert_any_transaction(self):
        assert self._SPY_TRANSACTIONS, 'No transactions performed'

    def assert_no_transactions(self):
        assert not self._SPY_TRANSACTIONS, 'Transactions performed'

    def assert_only_one_transaction_executed(self):
        assert len(self._SPY_TRANSACTIONS) == 1

    def assert_transaction_not_called(self, name: str):
        assert name not in self._SPY_TRANSACTIONS

    def assert_transaction(self, name: str, call_count: int = 1, **kwargs):

        # some transaction
        assert self._SPY_TRANSACTIONS, 'No transactions performed'
        assert name in self.TRANSACTIONS, f'"{name}" was nor performed'

        # this transaction
        transaction_executions = self._SPY_TRANSACTIONS[name]
        assert len(transaction_executions) == call_count, f'Transaction "{name}" was called an unexpected number of times'

        # transaction params
        agent_args, agent_kwargs = transaction_executions[0]  # use the first occurrence
        assert kwargs == agent_kwargs, 'Unexpected agent input'

    def assert_contract_calls(self, calls: Tuple[str]):
        for call_name in calls:
            assert call_name in self._SPY_CALLS, f'"{call_name}" was not called'


class MockStakingAgent(MockContractAgent, StakingEscrowAgent):

    CALLS = ('get_completed_work', )


class MockWorkLockAgent(MockContractAgent, WorkLockAgent):

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

    def __init__(self):

        # Allow for mocking
        economics = EconomicsFactory.get_economics(registry=Mock())

        self.ATTRS = {'boosting_refund': economics.worklock_boosting_refund_rate,
                      'slowing_refund': 1,  # TODO: another way to get this value?
                      'start_bidding_date': economics.bidding_start_date,
                      'end_bidding_date': economics.bidding_end_date,
                      'end_cancellation_date': economics.cancellation_end_date,
                      'minimum_allowed_bid': economics.worklock_min_allowed_bid,
                      'lot_value': economics.worklock_supply}

        super().__init__()


class MockContractAgency:

    # Test doubles
    DOUBLE_AGENTS = {WorkLockAgent: MockWorkLockAgent,
                     StakingEscrowAgent: MockStakingAgent}

    @classmethod
    def get_agent(cls, agent_class, *args, **kwargs):
        try:
            double = cls.DOUBLE_AGENTS[agent_class]
        except KeyError:
            return ValueError(f'No mock available for "{str(agent_class)}"')
        else:
            return double()

    @classmethod
    def get_agent_by_contract_name(cls, contract_name: str, *args, **kwargs):
        for agent, test_double, in cls.DOUBLE_AGENTS:
            if test_double.registry_contract_name == contract_name:
                return test_double
        else:
            return ValueError(f'No mock available for "{contract_name}"')

