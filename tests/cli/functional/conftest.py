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


import click
import os
import pytest
from eth_account.account import Account
from io import StringIO

from nucypher.blockchain.economics import EconomicsFactory
from nucypher.blockchain.eth.agents import ContractAgency
from nucypher.blockchain.eth.interfaces import BlockchainInterface, BlockchainInterfaceFactory
from nucypher.blockchain.eth.registry import InMemoryContractRegistry
from nucypher.blockchain.eth.signers import KeystoreSigner
from nucypher.characters.control.emitters import StdoutEmitter
from nucypher.config.characters import UrsulaConfiguration
from tests.constants import KEYFILE_NAME_TEMPLATE, MOCK_KEYSTORE_PATH, NUMBER_OF_MOCK_KEYSTORE_ACCOUNTS
from tests.fixtures import _make_testerchain, make_token_economics
from tests.mock.agents import FAKE_RECEIPT, MockContractAgency, MockNucypherToken, MockStakingAgent, MockWorkLockAgent
from tests.mock.interfaces import MockBlockchain, make_mock_registry_source_manager


@pytest.fixture(scope='module')
def monkeymodule():
    from _pytest.monkeypatch import MonkeyPatch
    mpatch = MonkeyPatch()
    yield mpatch
    mpatch.undo()


@pytest.fixture(scope='module', autouse=True)
def mock_contract_agency(monkeymodule, module_mocker, token_economics):
    monkeymodule.setattr(ContractAgency, 'get_agent', MockContractAgency.get_agent)
    module_mocker.patch.object(EconomicsFactory, 'get_economics', return_value=token_economics)
    yield MockContractAgency()
    monkeymodule.delattr(ContractAgency, 'get_agent')


@pytest.fixture(scope='module', autouse=True)
def mock_token_agent(mock_testerchain, token_economics, mock_contract_agency):
    mock_agent = mock_contract_agency.get_agent(MockNucypherToken)
    yield mock_agent
    mock_agent.reset()


@pytest.fixture(scope='module', autouse=True)
def mock_worklock_agent(mock_testerchain, token_economics, mock_contract_agency):
    mock_agent = mock_contract_agency.get_agent(MockWorkLockAgent)
    yield mock_agent
    mock_agent.reset()


@pytest.fixture(scope='module', autouse=True)
def mock_staking_agent(mock_testerchain, token_economics, mock_contract_agency):
    mock_agent = mock_contract_agency.get_agent(MockStakingAgent)
    yield mock_agent
    mock_agent.reset()


@pytest.fixture()
def mock_click_prompt(mocker):
    return mocker.patch.object(click, 'prompt')


@pytest.fixture()
def mock_click_confirm(mocker):
    return mocker.patch.object(click, 'confirm')


@pytest.fixture(scope='function')
def stdout_trap():
    trap = StringIO()
    yield trap
    trap.truncate(0)


@pytest.fixture()
def test_emitter(mocker, stdout_trap):
    mocker.patch('sys.stdout', new=stdout_trap)
    return StdoutEmitter()


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
    for i in range(NUMBER_OF_MOCK_KEYSTORE_ACCOUNTS):
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


@pytest.fixture(scope='function')
def patch_keystore(mock_accounts, monkeypatch, mocker):

    def successful_mock_keyfile_reader(_keystore, path):

        # Ensure the absolute path is passed to the keyfile reader
        assert MOCK_KEYSTORE_PATH in path
        full_path = path
        del path

        for filename, account in mock_accounts.items():  # Walk the mock filesystem
            if filename in full_path:
                break
        else:
            raise FileNotFoundError(f"No such file {full_path}")
        return account.address, dict(version=3, address=account.address)

    mocker.patch('os.listdir', return_value=list(mock_accounts.keys()))
    monkeypatch.setattr(KeystoreSigner, '_KeystoreSigner__read_keyfile', successful_mock_keyfile_reader)
    yield
    monkeypatch.delattr(KeystoreSigner, '_KeystoreSigner__read_keyfile')
