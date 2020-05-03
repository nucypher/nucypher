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

from nucypher.blockchain.economics import EconomicsFactory
from nucypher.blockchain.eth.agents import ContractAgency
from nucypher.blockchain.eth.interfaces import BlockchainInterface
from tests.mock.agents import MockWorkLockAgent, FAKE_RECEIPT


@pytest.fixture(scope='session', autouse=True)
def mock_interface(session_mocker):
    mock_transaction_sender = session_mocker.patch.object(BlockchainInterface, 'sign_and_broadcast_transaction')
    mock_transaction_sender.return_value = FAKE_RECEIPT
    return mock_transaction_sender


@pytest.fixture(scope='module')
def mock_worklock_agent(module_mocker, mock_testerchain, token_economics):
    special_agent = MockWorkLockAgent()
    module_mocker.patch.object(ContractAgency, 'get_agent', return_value=special_agent)
    module_mocker.patch.object(EconomicsFactory, 'get_economics', return_value=token_economics)
    return special_agent
