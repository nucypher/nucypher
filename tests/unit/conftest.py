import pytest
from eth_account.account import Account

from nucypher.blockchain.economics import EconomicsFactory
from nucypher.blockchain.eth.agents import ContractAgency, CoordinatorAgent
from nucypher.crypto.powers import TransactingPower
from nucypher.network.nodes import Teacher
from tests.mock.agents import MockContractAgency
from tests.mock.coordinator import MockCoordinatorV1
from tests.mock.interfaces import MockEthereumClient


@pytest.fixture(scope='function')
def mock_ethereum_client(mocker):
    web3_mock = mocker.Mock()
    mock_client = MockEthereumClient(w3=web3_mock)
    return mock_client


@pytest.fixture(scope='module', autouse=True)
def mock_transacting_power(module_mocker):
    module_mocker.patch.object(TransactingPower, 'unlock')


@pytest.fixture(scope='module', autouse=True)
def mock_contract_agency(module_mocker, application_economics):

    # Patch
    module_mocker.patch.object(EconomicsFactory, 'get_economics', return_value=application_economics)

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


@pytest.fixture(scope='session', autouse=True)
def mock_operator_bonding(session_mocker):
    session_mocker.patch.object(Teacher, '_operator_is_bonded', autospec=True)


# TODO: move to acceptance tests for prototyping
# @pytest.fixture(scope='session', autouse=True)
# def mock_coordinator(session_mocker):
#     class Contract:
#         functions = MockCoordinatorV1(60, 60)
#     session_mocker.patch.object(CoordinatorAgent, 'contract', return_value=Contract())
