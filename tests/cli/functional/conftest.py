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
from eth_account import Account

from nucypher.blockchain.economics import EconomicsFactory
from nucypher.blockchain.eth.agents import ContractAgency
from nucypher.blockchain.eth.interfaces import BlockchainInterface, BlockchainInterfaceFactory
from nucypher.blockchain.eth.registry import InMemoryContractRegistry
from nucypher.config.characters import UrsulaConfiguration
from tests.cli.functional.test_ursula_local_keystore_cli_functionality import NUMBER_OF_MOCK_ACCOUNTS, \
    KEYFILE_NAME_TEMPLATE
from tests.fixtures import _make_testerchain, make_token_economics
from tests.mock.interfaces import make_mock_registry_source_manager, MockBlockchain
from tests.mock.agents import FAKE_RECEIPT, MockContractAgency


@pytest.fixture(scope='module', autouse=True)
def mock_testerchain() -> MockBlockchain:
    BlockchainInterfaceFactory._interfaces = dict()
    testerchain = _make_testerchain(mock_backend=True)
    BlockchainInterfaceFactory.register_interface(interface=testerchain)
    yield testerchain


@pytest.fixture(scope='module')
def token_economics(mock_testerchain):
    return make_token_economics(blockchain=mock_testerchain)


@pytest.fixture(scope='module', autouse=True)
def mock_interface(module_mocker):
    mock_transaction_sender = module_mocker.patch.object(BlockchainInterface, 'sign_and_broadcast_transaction')
    mock_transaction_sender.return_value = FAKE_RECEIPT
    return mock_transaction_sender


@pytest.fixture(scope='module')
def test_registry():
    registry = InMemoryContractRegistry()
    return registry


@pytest.fixture(scope='module')
def test_registry_source_manager(mock_testerchain, test_registry):
    return make_mock_registry_source_manager(blockchain=mock_testerchain,
                                             test_registry=test_registry,
                                             mock_backend=True)


@pytest.fixture(scope='module', autouse=True)
def mock_contract_agency(module_mocker, token_economics):

    # Patch
    module_mocker.patch.object(EconomicsFactory, 'get_economics', return_value=token_economics)

    # Monkeypatch # TODO: Use better tooling for this monkeypatch?
    get_agent = ContractAgency.get_agent
    get_agent_by_name = ContractAgency.get_agent_by_contract_name
    ContractAgency.get_agent = MockContractAgency.get_agent
    ContractAgency.get_agent_by_contract_name = MockContractAgency.get_agent_by_contract_name

    # Test
    yield MockContractAgency()

    # Restore the monkey patching
    ContractAgency.get_agent = get_agent
    ContractAgency.get_agent_by_contract_name = get_agent_by_name


@pytest.fixture(scope='module')
def mock_accounts():
    accounts = dict()
    for i in range(NUMBER_OF_MOCK_ACCOUNTS):
        account = Account.create()
        filename = KEYFILE_NAME_TEMPLATE.format(month=i+1, address=account.address)
        accounts[filename] = account
    return accounts


@pytest.fixture(scope='module')
def worker_account(mock_accounts, mock_testerchain):
    account = list(mock_accounts.values())[0]
    return account


@pytest.fixture(scope='module')
def worker_address(worker_account):
    address = worker_account.address
    return address


@pytest.fixture(scope='module')
def custom_config_filepath(custom_filepath):
    filepath = os.path.join(custom_filepath, UrsulaConfiguration.generate_filename())
    return filepath
