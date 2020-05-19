from hexbytes import HexBytes
from typing import Callable, Generator, Type
from unittest.mock import Mock

from nucypher.blockchain.eth import agents
from nucypher.blockchain.eth.agents import ContractAgency, EthereumContractAgent
from nucypher.blockchain.eth.constants import NULL_ADDRESS
from nucypher.blockchain.eth.decorators import ContractInterfaces
from nucypher.blockchain.eth.interfaces import BlockchainInterfaceFactory
from tests.constants import MOCK_PROVIDER_URI

MOCK_TESTERCHAIN = BlockchainInterfaceFactory.get_or_create_interface(provider_uri=MOCK_PROVIDER_URI)
CURRENT_BLOCK = MOCK_TESTERCHAIN.w3.eth.getBlock(block_identifier='latest')

FAKE_RECEIPT = {'transactionHash': HexBytes(b'FAKE29890FAKE8349804'),
                'gasUsed': 1,
                'blockNumber': CURRENT_BLOCK.number,
                'blockHash': HexBytes(b'FAKE43434343FAKE43443434')}


def default_fake_transaction(*_a, **_kw) -> dict: return FAKE_RECEIPT


def default_fake_call(*_a, **_kw) -> 1: return 1


class MockContractAgent:

    # Meta
    MOCK_PREFIX = 'Mock'

    # Internal
    registry = Mock()
    blockchain = MOCK_TESTERCHAIN

    contract = Mock()
    contract_address = NULL_ADDRESS

    # API
    DEFAULT_TRANSACTION = default_fake_transaction()
    DEFAULT_CALL = default_fake_call()

    DEFAULTS = {
        ContractInterfaces.CALL: DEFAULT_CALL,
        ContractInterfaces.TRANSACTION: DEFAULT_TRANSACTION
    }

    MOCKS = list()

    def __init__(self, agent_class: Type[EthereumContractAgent]):
        self.agent_class = agent_class

    @classmethod
    def setup_mock(cls, agent_class: Type[EthereumContractAgent] = None) -> 'MockContractAgent':
        """Bind mock agent attributes to the *subclass* with default values"""
        instance = cls(agent_class=agent_class)
        methods_to_mock = instance.collect_real_methods()
        for agent_method in methods_to_mock:
            default_return = cls.DEFAULTS.get(agent_method.contract_api)
            setattr(cls, agent_method.__name__, Mock(return_value=default_return))
        return instance

    def __is_contract_method(self, method_name: str) -> bool:
        real_method = getattr(self.agent_class, method_name)
        method_is_callable = callable(real_method)
        method_is_contract_api = hasattr(real_method, "contract_api")  # TODO: Move string marker to constantr
        is_contract_method = method_is_callable and method_is_contract_api
        return is_contract_method

    def collect_real_methods(self) -> Generator[Callable, None, None]:
        agent_attrs = dir(self.agent_class)
        predicate = self.__is_contract_method
        methods = (getattr(self.agent_class, name) for name in agent_attrs if predicate(name))
        return methods

    def reset(self) -> None:
        # TODO: Upstream update
        pass


class MockContractAgency(ContractAgency):

    @classmethod
    def get_agent(cls, agent_class: Type[EthereumContractAgent], *args, **kwargs) -> MockContractAgent:
        mock_agent = MockContractAgent.setup_mock(agent_class=agent_class)
        return mock_agent

    @classmethod
    def get_agent_by_contract_name(cls, contract_name: str, *args, **kwargs) -> MockContractAgent:
        agent_name = super()._contract_name_to_agent_name(name=contract_name)
        agent_class = getattr(agents, agent_name)
        mock_agent = cls.get_agent(agent_class=agent_class)
        return mock_agent

