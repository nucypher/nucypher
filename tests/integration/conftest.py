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
from pathlib import Path

import pytest
from eth_account.account import Account

from nucypher.blockchain.economics import EconomicsFactory
from nucypher.blockchain.eth.agents import (
    AdjudicatorAgent,
    ContractAgency,
    MultiSigAgent,
    NucypherTokenAgent,
    PolicyManagerAgent,
    StakingEscrowAgent,
    WorkLockAgent
)
from nucypher.blockchain.eth.interfaces import BlockchainInterface
from nucypher.blockchain.eth.registry import InMemoryContractRegistry
from nucypher.blockchain.eth.signers import KeystoreSigner
from nucypher.config.characters import StakeHolderConfiguration, UrsulaConfiguration
from tests.constants import (
    KEYFILE_NAME_TEMPLATE,
    MOCK_KEYSTORE_PATH,
    MOCK_PROVIDER_URI,
    NUMBER_OF_MOCK_KEYSTORE_ACCOUNTS
)
from tests.fixtures import make_token_economics
from tests.mock.agents import MockContractAgency, MockContractAgent
from tests.mock.interfaces import MockBlockchain, mock_registry_source_manager
from tests.mock.io import MockStdinWrapper
from tests.utils.config import (
    make_alice_test_configuration,
    make_bob_test_configuration,
    make_ursula_test_configuration
)
from tests.utils.ursula import MOCK_URSULA_STARTING_PORT


@pytest.fixture(scope='function', autouse=True)
def mock_contract_agency(monkeypatch, module_mocker, token_economics):
    monkeypatch.setattr(ContractAgency, 'get_agent', MockContractAgency.get_agent)
    module_mocker.patch.object(EconomicsFactory, 'get_economics', return_value=token_economics)
    mock_agency = MockContractAgency()
    yield mock_agency
    mock_agency.reset()


@pytest.fixture(scope='function', autouse=True)
def mock_token_agent(mock_testerchain, token_economics, mock_contract_agency):
    mock_agent = mock_contract_agency.get_agent(NucypherTokenAgent)
    yield mock_agent
    mock_agent.reset()


@pytest.fixture(scope='function', autouse=True)
def mock_staking_agent(mock_testerchain, token_economics, mock_contract_agency, mocker):
    mock_agent = mock_contract_agency.get_agent(StakingEscrowAgent)

    # Handle the special case of commit_to_next_period, which returns a txhash due to the fire_and_forget option
    mock_agent.commit_to_next_period = mocker.Mock(return_value=MockContractAgent.FAKE_TX_HASH)

    yield mock_agent
    mock_agent.reset()


@pytest.fixture(scope='function', autouse=True)
def mock_adjudicator_agent(mock_testerchain, token_economics, mock_contract_agency):
    mock_agent = mock_contract_agency.get_agent(AdjudicatorAgent)
    yield mock_agent
    mock_agent.reset()


@pytest.fixture(scope='function', autouse=True)
def mock_policy_manager_agent(mock_testerchain, token_economics, mock_contract_agency):
    mock_agent = mock_contract_agency.get_agent(PolicyManagerAgent)
    yield mock_agent
    mock_agent.reset()


@pytest.fixture(scope='function', autouse=True)
def mock_multisig_agent(mock_testerchain, token_economics, mock_contract_agency):
    mock_agent = mock_contract_agency.get_agent(MultiSigAgent)
    yield mock_agent
    mock_agent.reset()


@pytest.fixture(scope='function', autouse=True)
def mock_worklock_agent(mock_testerchain, token_economics, mock_contract_agency):
    economics = token_economics

    mock_agent = mock_contract_agency.get_agent(WorkLockAgent)

    # Customize the mock agent
    mock_agent.boosting_refund = economics.worklock_boosting_refund_rate
    mock_agent.slowing_refund = 100
    mock_agent.start_bidding_date = economics.bidding_start_date
    mock_agent.end_bidding_date = economics.bidding_end_date
    mock_agent.end_cancellation_date = economics.cancellation_end_date
    mock_agent.minimum_allowed_bid = economics.worklock_min_allowed_bid
    mock_agent.lot_value = economics.worklock_supply

    yield mock_agent
    mock_agent.reset()


@pytest.fixture(scope='function')
def mock_stdin(mocker):

    mock = MockStdinWrapper()

    mocker.patch('sys.stdin', new=mock.mock_stdin)
    mocker.patch('getpass.getpass', new=mock.mock_getpass)

    yield mock

    # Sanity check.
    # The user is encouraged to `assert mock_stdin.empty()` explicitly in the test
    # right after the input-consuming function call.
    assert mock.empty(), "Stdin mock was not empty on teardown - some unclaimed input remained"


@pytest.fixture(scope='module', autouse=True)
def mock_testerchain(_mock_testerchain) -> MockBlockchain:
    yield _mock_testerchain


@pytest.fixture(scope='module')
def token_economics(mock_testerchain):
    return make_token_economics(blockchain=mock_testerchain)


@pytest.fixture(scope='module', autouse=True)
def mock_interface(module_mocker):
    mock_transaction_sender = module_mocker.patch.object(BlockchainInterface, 'sign_and_broadcast_transaction')
    mock_transaction_sender.return_value = MockContractAgent.FAKE_RECEIPT
    return mock_transaction_sender


@pytest.fixture(scope='module')
def test_registry():
    registry = InMemoryContractRegistry()
    return registry


@pytest.fixture(scope='module')
def test_registry_source_manager(mock_testerchain, test_registry):
    with mock_registry_source_manager(test_registry=test_registry) as real_inventory:
        yield real_inventory


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
def mock_account(mock_accounts):
    return list(mock_accounts.items())[0][1]


@pytest.fixture(scope='module')
def worker_account(mock_accounts, mock_testerchain):
    account = list(mock_accounts.values())[0]
    return account


@pytest.fixture(scope='module')
def worker_address(worker_account):
    address = worker_account.address
    return address


@pytest.fixture(scope='module')
def custom_config_filepath(custom_filepath: Path):
    filepath = custom_filepath / UrsulaConfiguration.generate_filename()
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

    mocker.patch('pathlib.Path.iterdir', return_value=[Path(key) for key in mock_accounts.keys()])
    monkeypatch.setattr(KeystoreSigner, '_KeystoreSigner__read_keystore', successful_mock_keyfile_reader)
    yield
    monkeypatch.delattr(KeystoreSigner, '_KeystoreSigner__read_keystore')


@pytest.fixture(scope='function')
def patch_stakeholder_configuration(mock_accounts, monkeypatch):
    def mock_read_configuration_file(filepath: Path) -> dict:
        return dict()

    monkeypatch.setattr(StakeHolderConfiguration, '_read_configuration_file', mock_read_configuration_file)
    yield
    monkeypatch.delattr(StakeHolderConfiguration, '_read_configuration_file')


@pytest.fixture(scope='function')
def mock_keystore(mocker):
    mocker.patch.object(KeystoreSigner, '_KeystoreSigner__read_keystore')


@pytest.fixture(scope="module")
def alice_blockchain_test_config(mock_testerchain, test_registry):
    config = make_alice_test_configuration(federated=False,
                                           provider_uri=MOCK_PROVIDER_URI,
                                           test_registry=test_registry,
                                           checksum_address=mock_testerchain.alice_account)
    yield config
    config.cleanup()


@pytest.fixture(scope="module")
def bob_blockchain_test_config(mock_testerchain, test_registry):
    config = make_bob_test_configuration(federated=False,
                                         provider_uri=MOCK_PROVIDER_URI,
                                         test_registry=test_registry,
                                         checksum_address=mock_testerchain.bob_account)
    yield config
    config.cleanup()


@pytest.fixture(scope="module")
def ursula_decentralized_test_config(mock_testerchain, test_registry):
    config = make_ursula_test_configuration(federated=False,
                                            provider_uri=MOCK_PROVIDER_URI,
                                            test_registry=test_registry,
                                            rest_port=MOCK_URSULA_STARTING_PORT,
                                            checksum_address=mock_testerchain.ursula_account(index=0))
    yield config
    config.cleanup()
