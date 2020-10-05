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

from enum import Enum

from constant_sorrow.constants import (CONTRACT_ATTRIBUTE, CONTRACT_CALL, TRANSACTION)
from hexbytes import HexBytes
from typing import Callable, Generator, Iterable, List, Type, Union
from unittest.mock import Mock

from nucypher.blockchain.eth import agents
from nucypher.blockchain.eth.agents import Agent, ContractAgency, EthereumContractAgent
from nucypher.blockchain.eth.constants import NULL_ADDRESS
from nucypher.blockchain.eth.interfaces import BlockchainInterfaceFactory
from tests.constants import MOCK_PROVIDER_URI
from tests.mock.interfaces import MockBlockchain

MOCK_TESTERCHAIN = MockBlockchain()
CACHED_MOCK_TESTERCHAIN = BlockchainInterfaceFactory.CachedInterface(interface=MOCK_TESTERCHAIN, emitter=None)
BlockchainInterfaceFactory._interfaces[MOCK_PROVIDER_URI] = CACHED_MOCK_TESTERCHAIN

CURRENT_BLOCK = MOCK_TESTERCHAIN.w3.eth.getBlock('latest')


class MockContractAgent:

    FAKE_TX_HASH = HexBytes(b'FAKE29890FAKE8349804')

    FAKE_RECEIPT = {'transactionHash': FAKE_TX_HASH,
                    'gasUsed': 1,
                    'blockNumber': CURRENT_BLOCK.number,
                    'blockHash': HexBytes(b'FAKE43434343FAKE43443434')}

    FAKE_CALL_RESULT = 1

    # Internal
    __COLLECTION_MARKER = "contract_api"  # decorator attribute
    __DEFAULTS = {
        CONTRACT_CALL: FAKE_CALL_RESULT,
        CONTRACT_ATTRIBUTE: FAKE_CALL_RESULT,
        TRANSACTION:  FAKE_RECEIPT,
    }

    _MOCK_METHODS = list()
    _REAL_METHODS = list()

    # Mock Nucypher Contract API
    contract = Mock()
    contract_address = NULL_ADDRESS

    # Mock Blockchain Interfaces
    registry = Mock()
    blockchain = MOCK_TESTERCHAIN

    def __init__(self, agent_class: Type[EthereumContractAgent]):
        """Bind mock agent attributes to the *subclass* with default values"""
        self.agent_class = agent_class
        self.__setup_mock(agent_class=agent_class)

    def __repr__(self) -> str:
        r = f'Mock{self.agent_class.__name__}(id={id(self)})'
        return r

    def __setup_mock(self, agent_class: Type[Agent]) -> None:

        api_methods: Iterable[Callable] = list(self.__collect_contract_api(agent_class=agent_class))
        mock_methods, mock_properties = list(), dict()

        for agent_interface in api_methods:

            # Handle
            try:
                # TODO: #2022: This might be a method also decorated @property
                # Get the inner function of the property
                real_method: Callable = agent_interface.fget  # Handle properties
            except AttributeError:
                real_method = agent_interface

            # Get
            interface = getattr(real_method, self.__COLLECTION_MARKER)
            default_return = self.__DEFAULTS.get(interface)

            # TODO: #2022 Special handling of PropertyMocks?
            # # Setup
            # if interface == CONTRACT_ATTRIBUTE:
            #     mock = PropertyMock()
            #     mock_properties[real_method.__name__] = mock
            # else:
            mock = Mock(return_value=default_return)

            # Mark
            setattr(mock, self.__COLLECTION_MARKER, interface)
            mock_methods.append(mock)

            # Bind
            setattr(self, real_method.__name__, mock)

        self._MOCK_METHODS = mock_methods
        self._REAL_METHODS = api_methods

    def __get_interface_calls(self, interface: Enum) -> List[Callable]:
        predicate = lambda method: bool(method.contract_api == interface)
        interface_calls = list(filter(predicate, self._MOCK_METHODS))
        return interface_calls

    @classmethod
    def __is_contract_method(cls, agent_class: Type[Agent], method_name: str) -> bool:
        method_or_property = getattr(agent_class, method_name)
        try:
            real_method: Callable = method_or_property.fget  # Property (getter)
        except AttributeError:
            real_method: Callable = method_or_property       # Method
        contract_api: bool = hasattr(real_method, cls.__COLLECTION_MARKER)
        return contract_api

    @classmethod
    def __collect_contract_api(cls, agent_class: Type[Agent]) -> Generator[Callable, None, None]:
        agent_attrs = dir(agent_class)
        predicate = cls.__is_contract_method
        methods = (getattr(agent_class, name) for name in agent_attrs if predicate(agent_class, name))
        return methods

    #
    # Test Utilities
    #

    @property
    def all_transactions(self) -> List[Callable]:
        interface = TRANSACTION
        transaction_functions = self.__get_interface_calls(interface=interface)
        return transaction_functions

    @property
    def contract_calls(self) -> List[Callable]:
        interface = CONTRACT_CALL
        transaction_functions = self.__get_interface_calls(interface=interface)
        return transaction_functions

    def get_unexpected_transactions(self, allowed: Union[Iterable[Callable], None]) -> List[Callable]:
        if allowed:
            predicate = lambda tx: tx not in allowed and tx.called
        else:
            predicate = lambda tx: tx.called
        unexpected_transactions = list(filter(predicate, self.all_transactions))
        return unexpected_transactions

    def assert_only_transactions(self, allowed: Iterable[Callable]) -> None:
        unexpected_transactions = self.get_unexpected_transactions(allowed=allowed)
        assert not bool(unexpected_transactions)

    def assert_no_transactions(self) -> None:
        unexpected_transactions = self.get_unexpected_transactions(allowed=None)
        assert not bool(unexpected_transactions)

    def reset(self, clear_side_effects: bool = True, clear_return_values: bool = True) -> None:
        for mock in self._MOCK_METHODS:
            mock.reset_mock(return_value=clear_return_values, side_effect=clear_side_effects)
            if clear_return_values:
                interface = getattr(mock, self.__COLLECTION_MARKER)
                default_return = self.__DEFAULTS.get(interface)
                mock.return_value = default_return


class MockContractAgency(ContractAgency):

    __agents = dict()

    @classmethod
    def get_agent(cls, agent_class: Type[Agent], *args, **kwargs) -> MockContractAgent:
        try:
            mock_agent = cls.__agents[agent_class]
        except KeyError:
            mock_agent = MockContractAgent(agent_class=agent_class)
            cls.__agents[agent_class] = mock_agent
        return mock_agent

    @classmethod
    def get_agent_by_contract_name(cls, contract_name: str, *args, **kwargs) -> MockContractAgent:
        agent_name = super()._contract_name_to_agent_name(name=contract_name)
        agent_class = getattr(agents, agent_name)
        mock_agent = cls.get_agent(agent_class=agent_class)
        return mock_agent

    @classmethod
    def reset(cls) -> None:
        for agent in cls.__agents.values():
            agent.reset()
