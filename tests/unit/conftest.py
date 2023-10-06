import pytest
from nucypher_core.ferveo import Keypair, Validator

from nucypher.blockchain.eth.actors import Operator
from nucypher.blockchain.eth.agents import ContractAgency
from nucypher.blockchain.eth.interfaces import BlockchainInterfaceFactory
from nucypher.blockchain.eth.registry import ContractRegistry
from nucypher.config.constants import TEMPORARY_DOMAIN
from nucypher.crypto.ferveo import dkg
from nucypher.crypto.powers import TransactingPower
from nucypher.network.nodes import Teacher
from tests.mock.interfaces import MockBlockchain, MockEthereumClient
from tests.utils.registry import MockRegistrySource, mock_registry_sources


def pytest_addhooks(pluginmanager):
    pluginmanager.set_blocked('ape_test')


@pytest.fixture(scope='module')
def test_registry(module_mocker):
    with mock_registry_sources(mocker=module_mocker):
        source = MockRegistrySource(domain=TEMPORARY_DOMAIN)
        yield ContractRegistry(source=source)


@pytest.fixture(scope='function')
def mock_ethereum_client(mocker):
    web3_mock = mocker.Mock()
    mock_client = MockEthereumClient(w3=web3_mock)
    return mock_client


@pytest.fixture(scope='module', autouse=True)
def mock_transacting_power(module_mocker):
    module_mocker.patch.object(TransactingPower, 'unlock')


@pytest.fixture(scope='module', autouse=True)
def mock_contract_agency():
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


@pytest.fixture(scope='session', autouse=True)
def mock_operator_bonding(session_mocker):
    session_mocker.patch.object(Teacher, '_operator_is_bonded', autospec=True)


@pytest.fixture(scope="module")
def testerchain(mock_testerchain, module_mocker) -> MockBlockchain:
    def always_use_mock(*a, **k):
        return mock_testerchain

    module_mocker.patch.object(
        BlockchainInterfaceFactory, "get_interface", always_use_mock
    )
    return mock_testerchain


@pytest.fixture(scope="module", autouse=True)
def staking_providers(testerchain, test_registry, monkeymodule):
    def faked(self, *args, **kwargs):
        return testerchain.stake_providers_accounts[
            testerchain.ursulas_accounts.index(self.transacting_power.account)
        ]

    Operator.get_staking_provider_address = faked
    return testerchain.stake_providers_accounts


@pytest.fixture(scope="module", autouse=True)
def mock_substantiate_stamp(module_mocker, monkeymodule):
    fake_signature = b"\xb1W5?\x9b\xbaix>'\xfe`\x1b\x9f\xeb*9l\xc0\xa7\xb9V\x9a\x83\x84\x04\x97\x0c\xad\x99\x86\x81W\x93l\xc3\xbde\x03\xcd\"Y\xce\xcb\xf7\x02z\xf6\x9c\xac\x84\x05R\x9a\x9f\x97\xf7\xa02\xb2\xda\xa1Gv\x01"
    from nucypher.characters.lawful import Ursula

    module_mocker.patch.object(Ursula, "_substantiate_stamp", autospec=True)
    module_mocker.patch.object(Ursula, "operator_signature", fake_signature)
    module_mocker.patch.object(Teacher, "validate_operator")


@pytest.fixture(scope="session")
def random_transcript(get_random_checksum_address):
    ritual_id = 0
    num_shares = 4
    threshold = 3
    validators = []
    for i in range(0, num_shares):
        validators.append(
            Validator(
                address=get_random_checksum_address(),
                public_key=Keypair.random().public_key(),
            )
        )

    validators.sort(key=lambda x: x.address)  # must be sorte

    transcript = dkg.generate_transcript(
        ritual_id=ritual_id,
        me=validators[0],
        shares=num_shares,
        threshold=threshold,
        nodes=validators,
    )

    return transcript
