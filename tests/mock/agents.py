from collections import defaultdict

from hexbytes import HexBytes
from typing import Tuple
from unittest.mock import Mock

from nucypher.blockchain.economics import EconomicsFactory
from nucypher.blockchain.eth.agents import NucypherTokenAgent, PolicyManagerAgent, StakingEscrowAgent, WorkLockAgent
from nucypher.blockchain.eth.constants import NULL_ADDRESS
from nucypher.blockchain.eth.interfaces import BlockchainInterfaceFactory
from tests.constants import MOCK_PROVIDER_URI

MOCK_TESTERCHAIN = BlockchainInterfaceFactory.get_or_create_interface(provider_uri=MOCK_PROVIDER_URI)
CURRENT_BLOCK = MOCK_TESTERCHAIN.w3.eth.getBlock(block_identifier='latest')

#
# Fixtures
#

FAKE_RECEIPT = {'transactionHash': HexBytes(b'FAKE29890FAKE8349804'),
                'gasUsed': 1,
                'blockNumber': CURRENT_BLOCK.number,
                'blockHash': HexBytes(b'FAKE43434343FAKE43443434')}


def default_fake_transaction(*_a, **_kw) -> dict:
    return FAKE_RECEIPT


def default_fake_call(*_a, **_kw) -> 1:
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
        self.__setup_mock()

    @classmethod
    def __setup_mock(cls) -> None:
        for call in cls.CALLS:
            setattr(cls, call, Mock(return_value=default_fake_call()))
        for tx in cls.TRANSACTIONS:
            setattr(cls, tx, Mock(return_value=default_fake_transaction()))

    def __record_tx(self, name: str, params: tuple) -> None:
        self._SPY_TRANSACTIONS[str(name)].append(params)

    def __record_call(self, name: str, params: tuple) -> None:
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

    #
    # Utils
    #

    @classmethod
    def reset(cls) -> None:
        cls._SPY_TRANSACTIONS.clear()
        cls._SPY_CALLS.clear()

    #
    # Assertions
    #

    def assert_any_transaction(self) -> None:
        assert self._SPY_TRANSACTIONS, 'No transactions performed'

    def assert_no_transactions(self) -> None:
        assert not self._SPY_TRANSACTIONS, 'Transactions performed'

    def assert_only_one_transaction_executed(self) -> None:
        fail = f"{len(self._SPY_TRANSACTIONS)} were performed ({', '.join(self._SPY_TRANSACTIONS)})."
        assert len(self._SPY_TRANSACTIONS) == 1, fail

    def assert_transaction_not_called(self, name: str) -> None:
        assert name not in self._SPY_TRANSACTIONS, f'Unexpected transaction call "{name}".'

    def assert_transaction(self, name: str, call_count: int = 1, **kwargs) -> None:

        # some transaction
        assert self._SPY_TRANSACTIONS, 'No transactions performed'
        assert name in self.TRANSACTIONS, f'"{name}" was not performed. Recorded txs: ({" ,".join(self._SPY_TRANSACTIONS)})'

        # this transaction
        transaction_executions = self._SPY_TRANSACTIONS[name]
        fail = f'Transaction "{name}" was called an unexpected number of times; ' \
               f'Expected {call_count} got {len(transaction_executions)}.'
        assert len(transaction_executions) == call_count, fail

        # transaction params
        agent_args, agent_kwargs = transaction_executions[0]  # use the first occurrence
        assert kwargs == agent_kwargs, 'Unexpected agent input'

    def assert_contract_calls(self, calls: Tuple[str]) -> None:
        for call_name in calls:
            assert call_name in self._SPY_CALLS, f'"{call_name}" was not called'


class MockNucypherToken(MockContractAgent, NucypherTokenAgent):
    """Look at me im a token!"""


class MockStakingAgent(MockContractAgent, StakingEscrowAgent):
    """dont forget the eggs!"""

    CALLS = ('get_completed_work', )


class MockPolicyManagerAgent(MockContractAgent, PolicyManagerAgent):
    """The best ethereum policy manager ever"""


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
    DOUBLE_AGENTS = {NucypherTokenAgent: MockNucypherToken,
                     StakingEscrowAgent: MockStakingAgent,
                     PolicyManagerAgent: MockPolicyManagerAgent,
                     WorkLockAgent: MockWorkLockAgent}

    class NoMockFound(ValueError):
        """Well we hadn't made one yet"""

    @classmethod
    def get_agent(cls, agent_class, *args, **kwargs) -> MockContractAgent:
        try:
            double = cls.DOUBLE_AGENTS[agent_class]
        except KeyError:
            raise ValueError(f'No mock class available for "{str(agent_class)}"')
        else:
            return double()

    @classmethod
    def get_agent_by_contract_name(cls, contract_name: str, *args, **kwargs) -> MockContractAgent:
        for agent, test_double in cls.DOUBLE_AGENTS.items():
            if test_double.registry_contract_name == contract_name:
                return test_double()
        else:
            raise ValueError(f'No mock available for "{contract_name}"')
