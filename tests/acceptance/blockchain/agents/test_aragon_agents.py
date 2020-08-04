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

import os

import pytest
from eth_tester.exceptions import TransactionFailed

from nucypher.blockchain.eth.agents import TokenManagerAgent


@pytest.fixture(scope='module')
def token_manager(testerchain, deploy_contract):  # TODO: Maybe we can mock the blockchain here
    contract, _ = deploy_contract('TokenManagerMock')
    return contract


@pytest.fixture(scope='module')
def agent(testerchain, token_manager) -> TokenManagerAgent:
    token_manager_agent = TokenManagerAgent(address=token_manager.address)
    return token_manager_agent


def test_forwarder(agent):
    callscript = os.urandom(100)
    function_call = agent._forward(callscript=callscript)
    assert function_call.fn_name == "forward"
    assert function_call.arguments == (callscript, )


def test_token_manager_methods(agent, get_random_checksum_address):

    holder = get_random_checksum_address()

    function_call = agent._mint(amount=42, receiver_address=holder)
    assert function_call.fn_name == "mint"
    assert function_call.arguments == (holder, 42)

    function_call = agent._issue(amount=42)
    assert function_call.fn_name == "issue"
    assert function_call.arguments == (42, )

    function_call = agent._assign(amount=42, receiver_address=holder)
    assert function_call.fn_name == "assign"
    assert function_call.arguments == (holder, 42)

    function_call = agent._burn(amount=42, holder_address=holder)
    assert function_call.fn_name == "burn"
    assert function_call.arguments == (holder, 42)
