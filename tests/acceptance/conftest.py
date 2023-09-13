import random

import pytest
from ape import project
from web3 import Web3

from nucypher.blockchain.eth.actors import Operator, Ritualist
from nucypher.blockchain.eth.agents import (
    ContractAgency,
    CoordinatorAgent,
    TACoApplicationAgent,
)
from nucypher.blockchain.eth.interfaces import BlockchainInterfaceFactory
from nucypher.blockchain.eth.networks import NetworksInventory
from nucypher.blockchain.eth.signers.software import Web3Signer
from nucypher.config.constants import TEMPORARY_DOMAIN
from nucypher.crypto.powers import CryptoPower, TransactingPower
from nucypher.policy.conditions.context import USER_ADDRESS_CONTEXT
from nucypher.policy.conditions.evm import RPCCondition
from nucypher.policy.conditions.lingo import ConditionLingo, ReturnValueTest
from nucypher.policy.conditions.time import TimeCondition
from nucypher.policy.payment import SubscriptionManagerPayment
from nucypher.utilities.logging import Logger
from tests.constants import (
    APE_TEST_CHAIN_ID,
    BONUS_TOKENS_FOR_TESTS,
    INSECURE_DEVELOPMENT_PASSWORD,
    TEST_ETH_PROVIDER_URI,
)
from tests.utils.ape import registry_from_ape_deployments
from tests.utils.blockchain import TesterBlockchain
from tests.utils.ursula import (
    mock_permitted_multichain_connections,
    setup_multichain_ursulas,
)

test_logger = Logger("acceptance-test-logger")

DEPENDENCY = project.dependencies["openzeppelin"]["4.9.1"]

#
# ERC-20
#
TOTAL_SUPPLY = Web3.to_wei(10_000_000_000, "ether")
NU_TOTAL_SUPPLY = Web3.to_wei(
    1_000_000_000, "ether"
)  # TODO NU(1_000_000_000, 'NU').to_units()

# TACo Application
MIN_AUTHORIZATION = Web3.to_wei(40_000, "ether")

MIN_OPERATOR_SECONDS = 24 * 60 * 60

REWARD_DURATION = 60 * 60 * 24 * 7  # one week in seconds
DEAUTHORIZATION_DURATION = 60 * 60 * 24 * 60  # 60 days in seconds

COMMITMENT_DURATION_1 = 182 * 60 * 24 * 60  # 182 days in seconds
COMMITMENT_DURATION_2 = 2 * COMMITMENT_DURATION_1  # 365 days in seconds

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
# Contracts
#


@pytest.fixture(scope="module")
def ritual_token(project, deployer_account):
    _ritual_token = deployer_account.deploy(project.RitualToken, TOTAL_SUPPLY)
    return _ritual_token


@pytest.fixture(scope="module")
def t_token(project, deployer_account):
    _t_token = deployer_account.deploy(project.TToken, TOTAL_SUPPLY)
    return _t_token


@pytest.fixture(scope="module")
def nu_token(project, deployer_account):
    _nu_token = deployer_account.deploy(project.NuCypherToken, NU_TOTAL_SUPPLY)
    return _nu_token


@pytest.fixture(scope="module")
def threshold_staking(project, deployer_account):
    _threshold_staking = deployer_account.deploy(
        project.ThresholdStakingForTACoApplicationMock
    )
    return _threshold_staking


@pytest.fixture(scope="module")
def proxy_admin(project, deployer_account):
    _proxy_admin = DEPENDENCY.ProxyAdmin.deploy(sender=deployer_account)
    return _proxy_admin


@pytest.fixture(scope="module")
def taco_application(project, deployer_account, t_token, threshold_staking):
    _taco_application = deployer_account.deploy(
        project.TACoApplication,
        t_token.address,
        threshold_staking.address,
        MIN_AUTHORIZATION,
        MIN_OPERATOR_SECONDS,
        REWARD_DURATION,
        DEAUTHORIZATION_DURATION,
        [COMMITMENT_DURATION_1, COMMITMENT_DURATION_2],
    )

    return _taco_application


@pytest.fixture(scope="module")
def taco_application_proxy(
    project, deployer_account, proxy_admin, taco_application, threshold_staking
):
    proxy = DEPENDENCY.TransparentUpgradeableProxy.deploy(
        taco_application.address,
        proxy_admin.address,
        b"",
        sender=deployer_account,
    )
    proxy_contract = project.TACoApplication.at(proxy.address)

    threshold_staking.setApplication(proxy_contract.address, sender=deployer_account)
    proxy_contract.initialize(sender=deployer_account)

    return proxy_contract


@pytest.fixture(scope="module")
def taco_child_application(project, taco_application, deployer_account, proxy_admin):
    _taco_child_application = deployer_account.deploy(
        project.TACoChildApplication, taco_application.address
    )

    return _taco_child_application


@pytest.fixture(scope="module")
def taco_child_application_proxy(
    project,
    deployer_account,
    proxy_admin,
    taco_child_application,
    taco_application_proxy,
):
    proxy = DEPENDENCY.TransparentUpgradeableProxy.deploy(
        taco_child_application.address,
        proxy_admin.address,
        b"",
        sender=deployer_account,
    )
    proxy_contract = project.TACoChildApplication.at(proxy.address)
    taco_application_proxy.setChildApplication(
        proxy_contract.address, sender=deployer_account
    )

    return proxy_contract


@pytest.fixture(scope="module")
def coordinator(project, deployer_account, taco_child_application_proxy, ritual_token):
    contract = deployer_account.deploy(
        project.Coordinator,
        taco_child_application_proxy.address,
        TIMEOUT,
        MAX_DKG_SIZE,
        deployer_account.address,
        ritual_token.address,
        FEE_RATE,
    )
    contract.makeInitiationPublic(sender=deployer_account)
    return contract


@pytest.fixture(scope="module")
def global_allow_list(project, deployer_account, coordinator):
    contract = deployer_account.deploy(
        project.GlobalAllowList,
        coordinator.address,
        deployer_account.address,
    )

    return contract


#
# Deployment/Blockchains
#

@pytest.fixture(scope="session", autouse=True)
def nucypher_contracts(project):
    nucypher_contracts_dependency_api = project.dependencies["nucypher-contracts"]
    # simply use first entry - could be from github ('main') or local ('local')
    _, nucypher_contracts = list(nucypher_contracts_dependency_api.items())[0]
    nucypher_contracts.compile()
    return nucypher_contracts


@pytest.fixture(scope='module', autouse=True)
def deployed_contracts(
    nucypher_contracts,
    ritual_token,
    t_token,
    nu_token,
    threshold_staking,
    proxy_admin,
    taco_application,
    taco_child_application,
    coordinator,
    global_allow_list,
):
    # TODO: can this be improved - eg. get it from the project fixture
    deployments = [
        ritual_token,
        t_token,
        nu_token,
        threshold_staking,
        threshold_staking,
        taco_application,
        taco_child_application,
        coordinator,
        global_allow_list,
    ]
    return deployments


@pytest.fixture(scope='module', autouse=True)
def test_registry(nucypher_contracts, deployed_contracts):
    registry = registry_from_ape_deployments(deployments=deployed_contracts)
    return registry


@pytest.fixture(scope='module')
def testerchain(project, test_registry) -> TesterBlockchain:
    # Extract the web3 provider containing EthereumTester from the ape project's chain manager
    provider = project.chain_manager.provider.web3.provider
    testerchain = TesterBlockchain(eth_provider=provider)
    BlockchainInterfaceFactory.register_interface(interface=testerchain, force=True)
    yield testerchain


#
# Staking
#
@pytest.fixture(scope="module")
def staking_providers(
    testerchain,
    test_registry,
    threshold_staking,
    taco_child_application,
    taco_application_agent,
):
    blockchain = taco_application_agent.blockchain
    minimum_stake = taco_application_agent.get_min_authorization()

    staking_providers = list()
    for provider_address, operator_address in zip(blockchain.stake_providers_accounts, blockchain.ursulas_accounts):
        provider_power = TransactingPower(account=provider_address, signer=Web3Signer(testerchain.client))
        provider_power.unlock(password=INSECURE_DEVELOPMENT_PASSWORD)

        # for a random amount
        amount = minimum_stake + random.randrange(BONUS_TOKENS_FOR_TESTS)

        # initialize threshold stake via threshold staking (permission-less mock)
        tx = threshold_staking.functions.setRoles(provider_address).transact()
        testerchain.wait_for_receipt(tx)

        # TODO: extract this to a fixture
        tx = threshold_staking.functions.authorizationIncreased(
            provider_address, 0, amount
        ).transact()
        testerchain.wait_for_receipt(tx)

        taco_application_agent.bond_operator(
            staking_provider=provider_address,
            operator=operator_address,
            transacting_power=provider_power,
        )

        operator_power = TransactingPower(
            account=operator_address, signer=Web3Signer(testerchain.client)
        )

        operator = Operator(
            is_me=True,
            operator_address=operator_address,
            domain=TEMPORARY_DOMAIN,
            registry=test_registry,
            transacting_power=operator_power,
            eth_provider_uri=testerchain.eth_provider_uri,
            signer=Web3Signer(testerchain.client),
            crypto_power=CryptoPower(power_ups=[operator_power]),
            payment_method=SubscriptionManagerPayment(
                eth_provider=testerchain.eth_provider_uri,
                network=TEMPORARY_DOMAIN,
                registry=test_registry,
            ),
        )
        operator.confirm_address()  # assume we always need a "pre-confirmed" operator for now.

        # TODO clean this up, perhaps with a fixture
        # update StakeInfo
        tx = taco_child_application.functions.updateOperator(
            provider_address,
            operator_address,
        ).transact()
        testerchain.wait_for_receipt(tx)

        tx = taco_child_application.functions.updateAmount(
            provider_address,
            amount,
        ).transact()
        testerchain.wait_for_receipt(tx)

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
        CoordinatorAgent, registry=test_registry, provider_uri=TEST_ETH_PROVIDER_URI
    )
    return coordinator


@pytest.fixture(scope="module", autouse=True)
def taco_application_agent(testerchain, test_registry):
    _taco_application_agent = ContractAgency.get_agent(
        TACoApplicationAgent,
        registry=test_registry,
        provider_uri=TEST_ETH_PROVIDER_URI,
    )

    return _taco_application_agent


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


@pytest.fixture
def time_condition():
    condition = TimeCondition(
        chain=APE_TEST_CHAIN_ID, return_value_test=ReturnValueTest(">", 0)
    )
    return condition


@pytest.fixture
def compound_blocktime_lingo():
    return {
        "version": ConditionLingo.VERSION,
        "condition": {
            "conditionType": "compound",
            "operator": "and",
            "operands": [
                {
                    "conditionType": "time",
                    "returnValueTest": {"value": "0", "comparator": ">"},
                    "method": "blocktime",
                    "chain": APE_TEST_CHAIN_ID,
                },
                {
                    "conditionType": "time",
                    "returnValueTest": {
                        "value": "99999999999999999",
                        "comparator": "<",
                    },
                    "method": "blocktime",
                    "chain": APE_TEST_CHAIN_ID,
                },
                {
                    "conditionType": "time",
                    "returnValueTest": {"value": "0", "comparator": ">"},
                    "method": "blocktime",
                    "chain": APE_TEST_CHAIN_ID,
                },
            ],
        },
    }


@pytest.fixture
def rpc_condition():
    condition = RPCCondition(
        method="eth_getBalance",
        chain=APE_TEST_CHAIN_ID,
        return_value_test=ReturnValueTest("==", Web3.to_wei(1_000_000, "ether")),
        parameters=[USER_ADDRESS_CONTEXT],
    )
    return condition


@pytest.fixture(scope="session", autouse=True)
def mock_condition_blockchains(session_mocker):
    """adds testerchain's chain ID to permitted conditional chains"""
    session_mocker.patch.dict(
        "nucypher.policy.conditions.evm._CONDITION_CHAINS",
        {APE_TEST_CHAIN_ID: "eth-tester/pyevm"},
    )

    session_mocker.patch.object(
        NetworksInventory, "get_polygon_chain_id", return_value=APE_TEST_CHAIN_ID
    )

    session_mocker.patch.object(
        NetworksInventory, "get_ethereum_chain_id", return_value=APE_TEST_CHAIN_ID
    )


@pytest.fixture(scope="module", autouse=True)
def mock_multichain_configuration(module_mocker, testerchain):
    module_mocker.patch.object(
        Ritualist, "_make_condition_provider", return_value=testerchain.provider
    )
