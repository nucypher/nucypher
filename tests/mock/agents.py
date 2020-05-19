from collections import defaultdict

from hexbytes import HexBytes
from typing import Callable, Tuple
from unittest.mock import Mock, _CallList

from nucypher.blockchain.economics import EconomicsFactory
from nucypher.blockchain.eth.agents import (
    NucypherTokenAgent,
    PolicyManagerAgent,
    StakingEscrowAgent,
    WorkLockAgent
)
from nucypher.blockchain.eth.constants import NULL_ADDRESS
from nucypher.blockchain.eth.decorators import _CONTRACT_TRANSACTIONS, _CONTRACT_CALLS
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

    MOCK_PREFIX = 'Mock'

    # Internal
    registry = Mock()
    blockchain = MOCK_TESTERCHAIN

    contract = Mock()
    contract_address = NULL_ADDRESS

    # API
    # TODO: Auto generate calls and txs from class inspection

    DEFAULT_TRANSACTION = default_fake_transaction()
    DEFAULT_CALL = default_fake_call()

    ATTRS = dict()
    CALLS = tuple()
    TRANSACTIONS = tuple()

    def __init__(self):
        self.setup_mock(agent_attrs=self.ATTRS)

    @classmethod
    def setup_mock(cls, agent_attrs: dict = None) -> None:
        """Bind mock agent attributes to the *subclass* with default values"""

        # Default mocks for decorated agent methods
        real_name = cls.__name__.strip(cls.MOCK_PREFIX)
        cls.CALLS = _CONTRACT_CALLS[real_name]
        cls.TRANSACTIONS = _CONTRACT_TRANSACTIONS[real_name]

        for call in cls.CALLS:
            llama = call.__name__
            setattr(cls, call.__name__, Mock(return_value=cls.DEFAULT_CALL))
        for tx in cls.TRANSACTIONS:
            setattr(cls, tx.__name__, Mock(return_value=cls.DEFAULT_TRANSACTION))

        # Explicit Attrs
        cls.ATTRS = agent_attrs
        if agent_attrs:
            for agent_method, mock_value in agent_attrs.items():
                setattr(cls, agent_method, mock_value)

    #
    # Utils
    #

    def reset(self):
        for func in (*self.CALLS, *self.TRANSACTIONS):
            if func.__name__ in self.ATTRS:
                return  # Skip Explicit
            mock = getattr(self, func.__name__)
            mock.call_args_list = _CallList()

    def __get_call_list(self, callables: Tuple[Callable]) -> defaultdict:
        result = defaultdict(list)
        for callable in callables:
            name = callable.__name__
            mock = getattr(self, name)
            calls = mock.call_args_list
            if calls:
                result[name].extend(calls)
        return result

    @property
    def spy_transactions(self) -> defaultdict:
        result = self.__get_call_list(callables=self.TRANSACTIONS)
        return result
            
    @property
    def spy_contract_calls(self) -> defaultdict:
        result = self.__get_call_list(callables=self.CALLS)
        return result

    #
    # Assertions
    #

    def assert_any_transaction(self) -> None:
        assert self.spy_transactions, 'No transactions performed'

    def assert_no_transactions(self) -> None:
        assert not self.spy_transactions, 'Transactions performed'

    def assert_only_one_transaction_executed(self) -> None:
        fail = f"{len(self.spy_transactions)} were performed ({', '.join(self.spy_transactions)})."
        assert len(self.spy_transactions) == 1, fail

    def assert_transaction_not_called(self, name: str) -> None:
        assert name not in self.spy_transactions, f'Unexpected transaction call "{name}".'

    def assert_contract_calls(self, calls: Tuple[str]) -> None:
        for call_name in calls:
            assert call_name in self.spy_contract_calls, f'"{call_name}" was not called'


class MockNucypherToken(MockContractAgent, NucypherTokenAgent):
    """Look at me im a token!"""


class MockStakingEscrowAgent(MockContractAgent, StakingEscrowAgent):
    """dont forget the eggs!"""


class MockPolicyManagerAgent(MockContractAgent, PolicyManagerAgent):
    """The best ethereum policy manager ever"""


class MockWorkLockAgent(MockContractAgent, WorkLockAgent):

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
                     StakingEscrowAgent: MockStakingEscrowAgent,
                     PolicyManagerAgent: MockPolicyManagerAgent,
                     WorkLockAgent: MockWorkLockAgent}

    AGENTS = dict()

    class NoMockFound(ValueError):
        """Well we hadn't made one yet"""

    @classmethod
    def get_agent(cls, agent_class, *args, **kwargs) -> MockContractAgent:
        if MockContractAgent.MOCK_PREFIX not in str(agent_class.__name__):
            try:
                double = cls.DOUBLE_AGENTS[agent_class]
            except KeyError:
                raise ValueError(f'No mock class available for "{str(agent_class)}"')
            else:
                agent_class = double
        try:
            agent = cls.AGENTS[agent_class]
        except KeyError:
            agent = agent_class()
            cls.AGENTS[agent_class] = agent_class()

        return agent

    @classmethod
    def get_agent_by_contract_name(cls, contract_name: str, *args, **kwargs) -> MockContractAgent:
        for agent, test_double in cls.DOUBLE_AGENTS.items():
            if test_double.registry_contract_name == contract_name:
                return cls.get_agent(agent_class=test_double)
        else:
            raise ValueError(f'No mock available for "{contract_name}"')
