import random

import maya
import pytest
from web3 import Web3

import tests
from nucypher.blockchain.eth.actors import Operator
from nucypher.blockchain.eth.agents import (
    ContractAgency,
    CoordinatorAgent,
    TACoApplicationAgent,
    TACoChildApplicationAgent,
)
from nucypher.blockchain.eth.interfaces import BlockchainInterfaceFactory
from nucypher.blockchain.eth.registry import ContractRegistry, RegistrySourceManager
from nucypher.policy.conditions.evm import RPCCondition
from nucypher.utilities.logging import Logger
from tests.constants import (
    BONUS_TOKENS_FOR_TESTS,
    MIN_OPERATOR_SECONDS,
    TEMPORARY_DOMAIN,
    TEST_ETH_PROVIDER_URI,
    TESTERCHAIN_CHAIN_ID,
)
from tests.utils.blockchain import ReservedTestAccountManager, TesterBlockchain
from tests.utils.registry import ApeRegistrySource
from tests.utils.ursula import (
    mock_permitted_multichain_connections,
    setup_multichain_ursulas,
)

test_logger = Logger("acceptance-test-logger")

ONE_DAY = 24 * 60 * 60

# ERC-20
TOTAL_SUPPLY = Web3.to_wei(11_000_000_000, "ether")
NU_TOTAL_SUPPLY = Web3.to_wei(
    1_000_000_000, "ether"
)  # TODO NU(1_000_000_000, 'NU').to_units()

# TACo Application
MIN_AUTHORIZATION = Web3.to_wei(40_000, "ether")

REWARD_DURATION = 7 * ONE_DAY  # one week in seconds
DEAUTHORIZATION_DURATION = 60 * ONE_DAY  # 60 days in seconds

COMMITMENT_DURATION_1 = 182 * ONE_DAY  # 182 days in seconds
COMMITMENT_DURATION_2 = 2 * COMMITMENT_DURATION_1  # 365 days in seconds

COMMITMENT_DEADLINE = 100 * ONE_DAY  # 100 days after deployment

PENALTY_DEFAULT = 1000  # 10% penalty
PENALTY_INCREMENT = 2500  # 25% penalty increment
PENALTY_DURATION = ONE_DAY  # 1 day in seconds


# Coordinator
TIMEOUT = 3600
MAX_DKG_SIZE = 8
FEE_RATE = 1


#
# General
#


@pytest.fixture(scope="module")
def monkeymodule():
    from _pytest.monkeypatch import MonkeyPatch

    mpatch = MonkeyPatch()
    yield mpatch
    mpatch.undo()


#
# Accounts
#


@pytest.fixture(scope="session")
def accounts():
    return ReservedTestAccountManager()


@pytest.fixture(scope="module")
def deployer_account(accounts):
    return accounts[0]


@pytest.fixture(scope="module")
def initiator(testerchain, alice, ritual_token, deployer_account):
    """Returns the Initiator, funded with RitualToken"""
    # transfer ritual token to alice (initiator)
    ritual_token.transfer(
        alice.transacting_power.account,
        Web3.to_wei(1, "ether"),
        sender=deployer_account,
    )
    return alice


#
# Contracts Dependencies
#


@pytest.fixture(scope="session", autouse=True)
def nucypher_dependency(project):
    nucypher_contracts_dependency_api = project.dependencies["nucypher-contracts"]
    # simply use first entry - could be from github ('main') or local ('local')
    _, nucypher_dependency = list(nucypher_contracts_dependency_api.items())[0]
    return nucypher_dependency


@pytest.fixture(scope="session", autouse=True)
def oz_dependency(project):
    _oz_dependency = project.dependencies["openzeppelin"]["5.0.0"]
    return _oz_dependency


#
# Contracts
#


@pytest.fixture(scope="module")
def ritual_token(project, deployer_account):
    _ritual_token = deployer_account.deploy(project.RitualToken, TOTAL_SUPPLY)
    return _ritual_token


@pytest.fixture(scope="module")
def t_token(nucypher_dependency, deployer_account):
    _t_token = deployer_account.deploy(nucypher_dependency.TestToken, TOTAL_SUPPLY)
    return _t_token


@pytest.fixture(scope="module")
def nu_token(nucypher_dependency, deployer_account):
    _nu_token = deployer_account.deploy(
        nucypher_dependency.NuCypherToken, NU_TOTAL_SUPPLY
    )
    return _nu_token


@pytest.fixture(scope="module")
def threshold_staking(nucypher_dependency, deployer_account):
    _threshold_staking = deployer_account.deploy(
        nucypher_dependency.TestnetThresholdStaking
    )
    return _threshold_staking


@pytest.fixture(scope="module")
def taco_application(
    oz_dependency,
    nucypher_dependency,
    deployer_account,
    t_token,
    threshold_staking,
):
    taco_application_implementation = deployer_account.deploy(
        nucypher_dependency.TACoApplication,
        t_token.address,
        threshold_staking.address,
        MIN_AUTHORIZATION,
        MIN_OPERATOR_SECONDS,
        REWARD_DURATION,
        DEAUTHORIZATION_DURATION,
        [COMMITMENT_DURATION_1, COMMITMENT_DURATION_2],
        maya.now().epoch + COMMITMENT_DEADLINE,
        PENALTY_DEFAULT,
        PENALTY_DURATION,
        PENALTY_INCREMENT,
    )

    proxy = deployer_account.deploy(
        oz_dependency.TransparentUpgradeableProxy,
        taco_application_implementation.address,
        deployer_account.address,
        b"",
    )
    proxy_contract = nucypher_dependency.TACoApplication.at(proxy.address)

    threshold_staking.setApplication(proxy_contract.address, sender=deployer_account)
    proxy_contract.initialize(sender=deployer_account)

    return proxy_contract


@pytest.fixture(scope="module")
def taco_child_application(
    oz_dependency,
    nucypher_dependency,
    deployer_account,
    taco_application,
):
    taco_child_application_implementation = deployer_account.deploy(
        nucypher_dependency.TACoChildApplication,
        taco_application.address,
        MIN_AUTHORIZATION,
    )

    proxy = deployer_account.deploy(
        oz_dependency.TransparentUpgradeableProxy,
        taco_child_application_implementation.address,
        deployer_account.address,
        b"",
    )
    proxy_contract = nucypher_dependency.TACoChildApplication.at(proxy.address)
    taco_application.setChildApplication(
        proxy_contract.address, sender=deployer_account
    )

    return proxy_contract


@pytest.fixture(scope="module")
def adjudicator(module_mocker, get_random_checksum_address):
    _adjudicator = module_mocker.Mock()
    _adjudicator.address = get_random_checksum_address()
    return _adjudicator


@pytest.fixture(scope="module")
def coordinator(
    oz_dependency,
    nucypher_dependency,
    deployer_account,
    taco_child_application,
    ritual_token,
    adjudicator,
):
    _coordinator = deployer_account.deploy(
        nucypher_dependency.Coordinator,
        taco_child_application.address,
    )

    encoded_initializer_function = _coordinator.initialize.encode_input(
        TIMEOUT, MAX_DKG_SIZE, deployer_account.address
    )
    proxy = deployer_account.deploy(
        oz_dependency.TransparentUpgradeableProxy,
        _coordinator.address,
        deployer_account.address,
        encoded_initializer_function,
    )

    proxy_contract = nucypher_dependency.Coordinator.at(proxy.address)
    taco_child_application.initialize(
        proxy_contract.address, adjudicator.address, sender=deployer_account
    )
    return proxy_contract


@pytest.fixture(scope="module")
def fee_model(nucypher_dependency, deployer_account, coordinator, ritual_token):
    contract = deployer_account.deploy(
        nucypher_dependency.FlatRateFeeModel,
        coordinator.address,
        ritual_token.address,
        FEE_RATE,
    )
    treasury_role = coordinator.TREASURY_ROLE()
    coordinator.grantRole(
        treasury_role, deployer_account.address, sender=deployer_account
    )
    coordinator.approveFeeModel(contract.address, sender=deployer_account)

    return contract


@pytest.fixture(scope="module")
def global_allow_list(nucypher_dependency, deployer_account, coordinator):
    contract = deployer_account.deploy(
        nucypher_dependency.GlobalAllowList,
        coordinator.address,
    )

    return contract


@pytest.fixture(scope="module")
def subscription_manager(nucypher_dependency, deployer_account):
    _subscription_manager = deployer_account.deploy(
        nucypher_dependency.SubscriptionManager,
    )
    return _subscription_manager

#
# Deployment/Blockchains
#


@pytest.fixture(scope="module", autouse=True)
def deployed_contracts(
    ritual_token,
    t_token,
    nu_token,
    threshold_staking,
    taco_application,
    taco_child_application,
    coordinator,
    fee_model,
    global_allow_list,
    subscription_manager,
):
    # TODO: can this be improved - eg. get it from the project fixture
    deployments = [
        ritual_token,
        t_token,
        nu_token,
        threshold_staking,
        taco_application,
        taco_child_application,
        coordinator,
        fee_model,
        global_allow_list,
        subscription_manager,
    ]
    ApeRegistrySource.set_deployments(deployments)
    return deployments


@pytest.fixture(scope="module", autouse=True)
def test_registry(deployed_contracts, module_mocker):
    with tests.utils.registry.mock_registry_sources(mocker=module_mocker):
        RegistrySourceManager._FALLBACK_CHAIN = (ApeRegistrySource,)
        source = ApeRegistrySource(domain=TEMPORARY_DOMAIN)
        registry = ContractRegistry(source=source)
        yield registry


@pytest.mark.usefixtures("test_registry")
@pytest.fixture(scope="module")
def testerchain(project, clock, accounts) -> TesterBlockchain:
    # Extract the web3 provider containing EthereumTester from the ape project's chain manager
    provider = project.chain_manager.provider.web3.provider
    testerchain = TesterBlockchain(provider=provider)
    testerchain.tx_machine._task.clock = clock
    BlockchainInterfaceFactory.register_interface(interface=testerchain, force=True)
    yield testerchain


#
# Staking
#


@pytest.fixture(scope="module")
def staking_providers(
    deployer_account,
    accounts,
    testerchain,
    threshold_staking,
    taco_application,
):
    minimum_stake = taco_application.minimumAuthorization()

    staking_providers = list()
    for provider_address, operator_address in zip(
        accounts.staking_providers_accounts, accounts.ursulas_accounts
    ):
        # for a random amount
        amount = minimum_stake + random.randrange(BONUS_TOKENS_FOR_TESTS)

        # initialize threshold stake via threshold staking (permission-less mock)
        threshold_staking.setRoles(provider_address, sender=deployer_account)

        threshold_staking.authorizationIncreased(
            provider_address, 0, amount, sender=deployer_account
        )

        taco_application.bondOperator(
            provider_address,
            operator_address,
            sender=accounts[provider_address],
        )

        # track
        staking_providers.append(provider_address)

    yield staking_providers


#
# Agents
#


@pytest.fixture(scope="module", autouse=True)
def coordinator_agent(testerchain, test_registry):
    """Creates a coordinator agent"""
    coordinator = ContractAgency.get_agent(
        CoordinatorAgent,
        registry=test_registry,
        blockchain_endpoint=TEST_ETH_PROVIDER_URI,
    )
    return coordinator


@pytest.fixture(scope="module", autouse=True)
def taco_application_agent(test_registry):
    _taco_application_agent = ContractAgency.get_agent(
        TACoApplicationAgent,
        registry=test_registry,
        blockchain_endpoint=TEST_ETH_PROVIDER_URI,
    )

    return _taco_application_agent


@pytest.fixture(scope="module", autouse=True)
def taco_child_application_agent(testerchain, test_registry):
    _taco_child_application_agent = ContractAgency.get_agent(
        TACoChildApplicationAgent,
        registry=test_registry,
        blockchain_endpoint=TEST_ETH_PROVIDER_URI,
    )

    return _taco_child_application_agent


#
# Conditions
#

@pytest.fixture(scope="module")
def mock_rpc_condition(module_mocker, testerchain, monkeymodule):
    def configure_mock(condition, provider, *args, **kwargs):
        condition.provider = provider
        return testerchain.w3

    monkeymodule.setattr(RPCCondition, "_configure_w3", configure_mock)
    configure_spy = module_mocker.spy(RPCCondition, "_configure_w3")

    chain_id_check_mock = module_mocker.patch.object(RPCCondition, "_check_chain_id")
    return configure_spy, chain_id_check_mock


@pytest.fixture(scope="module")
def multichain_ids(module_mocker):
    ids = mock_permitted_multichain_connections(mocker=module_mocker)
    return ids


@pytest.fixture(scope="module")
def multichain_ursulas(ursulas, multichain_ids, mock_rpc_condition):
    setup_multichain_ursulas(ursulas=ursulas, chain_ids=multichain_ids)
    return ursulas


@pytest.fixture(scope="module", autouse=True)
def mock_condition_blockchains(module_mocker):
    """adds testerchain's chain ID to permitted conditional chains"""
    module_mocker.patch.dict(
        "nucypher.policy.conditions.evm._CONDITION_CHAINS",
        {TESTERCHAIN_CHAIN_ID: "eth-tester/pyevm"},
    )

    module_mocker.patch(
        "nucypher.blockchain.eth.domains.get_domain", return_value=TEMPORARY_DOMAIN
    )


@pytest.fixture(scope="module", autouse=True)
def mock_multichain_configuration(module_mocker, testerchain):
    module_mocker.patch.object(
        Operator, "_make_condition_provider", return_value=testerchain.provider
    )
