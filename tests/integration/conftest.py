import os
from pathlib import Path
from typing import Iterable, Optional

import pytest
from eth_account.account import Account

from nucypher.blockchain.eth.actors import Operator
from nucypher.blockchain.eth.agents import (
    ContractAgency,
    CoordinatorAgent,
    StakingProvidersReservoir,
    TACoApplicationAgent,
    TACoChildApplicationAgent,
)
from nucypher.blockchain.eth.clients import EthereumClient
from nucypher.blockchain.eth.interfaces import (
    BlockchainInterface,
    BlockchainInterfaceFactory,
)
from nucypher.blockchain.eth.networks import (
    EthChain,
    NetworksInventory,
    PolygonChain,
    TACoDomain,
)
from nucypher.blockchain.eth.registry import (
    ContractRegistry,
)
from nucypher.blockchain.eth.signers import KeystoreSigner
from nucypher.blockchain.eth.signers.software import Web3Signer
from nucypher.characters.lawful import Ursula
from nucypher.cli.types import ChecksumAddress
from nucypher.config.characters import UrsulaConfiguration
from nucypher.config.constants import TEMPORARY_DOMAIN
from nucypher.crypto.powers import TransactingPower
from nucypher.network.nodes import Teacher
from tests.constants import (
    KEYFILE_NAME_TEMPLATE,
    MOCK_KEYSTORE_PATH,
    NUMBER_OF_MOCK_KEYSTORE_ACCOUNTS,
    TESTERCHAIN_CHAIN_ID,
)
from tests.mock.interfaces import MockBlockchain
from tests.mock.io import MockStdinWrapper
from tests.utils.registry import MockRegistrySource, mock_registry_sources
from tests.utils.ursula import (
    mock_permitted_multichain_connections,
    setup_multichain_ursulas,
)


def pytest_addhooks(pluginmanager):
    pluginmanager.set_blocked('ape_test')


@pytest.fixture(scope="module", autouse=True)
def mock_sample_reservoir(testerchain, mock_contract_agency):
    def mock_reservoir(
        without: Optional[Iterable[ChecksumAddress]] = None, *args, **kwargs
    ):
        addresses = {
            address: 1
            for address in testerchain.stake_providers_accounts
            if address not in without
        }
        return StakingProvidersReservoir(addresses)

    mock_agent = mock_contract_agency.get_agent(TACoApplicationAgent)
    mock_agent.get_staking_provider_reservoir = mock_reservoir


@pytest.fixture(scope="function")
def mock_sign_message(mocker):
    mocked_sign_message = mocker.patch.object(
        Web3Signer, "sign_message", return_value=os.urandom(32)
    )
    return mocked_sign_message


@pytest.fixture(scope="function", autouse=True)
def mock_taco_application_agent(testerchain, mock_contract_agency):
    mock_agent = mock_contract_agency.get_agent(TACoApplicationAgent)
    yield mock_agent
    mock_agent.reset()


@pytest.fixture(scope="function", autouse=True)
def mock_taco_child_application_agent(testerchain, mock_contract_agency):
    mock_agent = mock_contract_agency.get_agent(TACoChildApplicationAgent)
    yield mock_agent
    mock_agent.reset()


@pytest.fixture(scope="function", autouse=True)
def mock_coordinator_agent(testerchain, mock_contract_agency):
    from tests.mock.coordinator import MockCoordinatorAgent

    mock_agent = MockCoordinatorAgent(blockchain=testerchain)
    mock_contract_agency._MockContractAgency__agents[CoordinatorAgent] = mock_agent
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


@pytest.fixture(scope="module")
def testerchain(mock_testerchain, module_mocker) -> MockBlockchain:
    def always_use_mock(*a, **k):
        return mock_testerchain

    module_mocker.patch.object(
        BlockchainInterfaceFactory, "get_interface", always_use_mock
    )
    return mock_testerchain


@pytest.fixture(scope='module', autouse=True)
def mock_interface(module_mocker):
    # Generic Interface
    mock_transaction_sender = module_mocker.patch.object(BlockchainInterface, 'sign_and_broadcast_transaction')
    mock_transaction_sender.return_value = MockBlockchain.FAKE_RECEIPT
    return mock_transaction_sender


@pytest.fixture(scope='module')
def test_registry():
    with mock_registry_sources():
        mock_source = MockRegistrySource(domain=TEMPORARY_DOMAIN)
        registry = ContractRegistry(source=mock_source)
        yield registry


@pytest.fixture(scope='module', autouse=True)
def mock_contract_agency():
    # Patch
    from tests.mock.agents import MockContractAgency

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
def agency(mock_contract_agency):
    yield mock_contract_agency


@pytest.fixture(scope="function")
def mock_funding_and_bonding(
    testerchain, mocker, mock_taco_application_agent, mock_taco_child_application_agent
):
    # funding
    mocker.patch.object(EthereumClient, "get_balance", return_value=1)

    # bonding
    staking_provider = testerchain.stake_providers_accounts[0]
    mock_taco_application_agent.get_staking_provider_from_operator.return_value = (
        staking_provider
    )
    mock_taco_child_application_agent.staking_provider_from_operator.return_value = (
        staking_provider
    )


@pytest.fixture(scope="module")
def mock_accounts():
    accounts = dict()
    for i in range(NUMBER_OF_MOCK_KEYSTORE_ACCOUNTS):
        account = Account.create()
        filename = KEYFILE_NAME_TEMPLATE.format(month=i + 1, address=account.address)
        accounts[filename] = account
    return accounts


@pytest.fixture(scope='module')
def mock_account(mock_accounts):
    return list(mock_accounts.items())[0][1]


@pytest.fixture(scope='module')
def operator_account(mock_accounts, testerchain):
    account = list(mock_accounts.values())[0]
    return account


@pytest.fixture(scope='module')
def operator_address(operator_account):
    address = operator_account.address
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
def mock_keystore(mocker):
    mocker.patch.object(KeystoreSigner, '_KeystoreSigner__read_keystore')


@pytest.fixture(scope="module", autouse=True)
def mock_substantiate_stamp(module_mocker, monkeymodule):
    fake_signature = b'\xb1W5?\x9b\xbaix>\'\xfe`\x1b\x9f\xeb*9l\xc0\xa7\xb9V\x9a\x83\x84\x04\x97\x0c\xad\x99\x86\x81W\x93l\xc3\xbde\x03\xcd"Y\xce\xcb\xf7\x02z\xf6\x9c\xac\x84\x05R\x9a\x9f\x97\xf7\xa02\xb2\xda\xa1Gv\x01'
    module_mocker.patch.object(Ursula, "_substantiate_stamp", autospec=True)
    module_mocker.patch.object(Ursula, "operator_signature", fake_signature)
    module_mocker.patch.object(Teacher, "validate_operator")


@pytest.fixture(scope="module", autouse=True)
def mock_transacting_power(module_mocker, monkeymodule):
    module_mocker.patch.object(TransactingPower, "unlock")


@pytest.fixture(scope="module")
def real_operator_get_staking_provider_address():
    _real_get_staking_provider_address = Operator.get_staking_provider_address
    return _real_get_staking_provider_address


@pytest.mark.usefixtures("monkeymodule")
@pytest.fixture(scope="module", autouse=True)
def staking_providers(real_operator_get_staking_provider_address, testerchain):
    def faked(self, *args, **kwargs):
        return testerchain.stake_providers_accounts[testerchain.ursulas_accounts.index(self.transacting_power.account)]

    Operator.get_staking_provider_address = faked
    return testerchain.stake_providers_accounts


@pytest.fixture(scope="module")
def monkeypatch_get_staking_provider_from_operator(monkeymodule):
    monkeymodule.setattr(
        Operator,
        "get_staking_provider_address",
        lambda self: self.transacting_power.account,
    )


@pytest.fixture(scope="session", autouse=True)
def mock_condition_blockchains(session_mocker):
    """adds testerchain's chain ID to permitted conditional chains"""
    session_mocker.patch.dict(
        "nucypher.policy.conditions.evm._CONDITION_CHAINS",
        {TESTERCHAIN_CHAIN_ID: "eth-tester/pyevm"},
    )

    testing_network = TACoDomain(
        TEMPORARY_DOMAIN, EthChain.TESTERCHAIN, PolygonChain.TESTERCHAIN
    )

    session_mocker.patch.object(
        NetworksInventory, "from_domain_name", return_value=testing_network
    )


@pytest.fixture(scope="module")
def multichain_ids(module_mocker):
    ids = mock_permitted_multichain_connections(mocker=module_mocker)
    return ids


@pytest.fixture(scope="module")
def multichain_ursulas(ursulas, multichain_ids):
    setup_multichain_ursulas(ursulas=ursulas, chain_ids=multichain_ids)
    return ursulas
