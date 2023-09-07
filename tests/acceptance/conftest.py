import os
import random

import pytest
from web3 import Web3

from nucypher.blockchain.eth.actors import Operator, Ritualist
from nucypher.blockchain.eth.agents import (
    ContractAgency,
    CoordinatorAgent,
    PREApplicationAgent,
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
from tests.acceptance.constants import APE_TEST_CHAIN_ID
from tests.constants import (
    BONUS_TOKENS_FOR_TESTS,
    GLOBAL_ALLOW_LIST,
    INSECURE_DEVELOPMENT_PASSWORD,
    MOCK_STAKING_CONTRACT_NAME,
    RITUAL_TOKEN,
    STAKE_INFO,
    TEST_ETH_PROVIDER_URI,
)
from tests.utils.ape import (
    deploy_contracts as ape_deploy_contracts,
)
from tests.utils.ape import (
    registry_from_ape_deployments,
)
from tests.utils.blockchain import TesterBlockchain
from tests.utils.ursula import (
    mock_permitted_multichain_connections,
    setup_multichain_ursulas,
)

test_logger = Logger("acceptance-test-logger")


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


@pytest.fixture(scope='session', autouse=True)
def test_contracts(project):
    return project.contracts


@pytest.fixture(scope="session", autouse=True)
def nucypher_contracts(project):
    nucypher_contracts_dependency_api = project.dependencies["nucypher-contracts"]
    # simply use first entry - could be from github ('main') or local ('local')
    _, nucypher_contracts = list(nucypher_contracts_dependency_api.items())[0]
    nucypher_contracts.compile()
    return nucypher_contracts


@pytest.fixture(scope='module', autouse=True)
def deploy_contracts(nucypher_contracts, test_contracts, accounts):
    deployments = ape_deploy_contracts(
        nucypher_contracts=nucypher_contracts,
        test_contracts=test_contracts,
        accounts=accounts,
    )
    return deployments


@pytest.fixture()
def deployer_account(accounts):
    return accounts[0]


@pytest.fixture(scope='module', autouse=True)
def test_registry(nucypher_contracts, deploy_contracts):
    registry = registry_from_ape_deployments(nucypher_contracts, deployments=deploy_contracts)
    return registry


@pytest.fixture(scope='module')
def testerchain(project, test_registry) -> TesterBlockchain:
    # Extract the web3 provider containing EthereumTester from the ape project's chain manager
    provider = project.chain_manager.provider.web3.provider
    testerchain = TesterBlockchain(eth_provider=provider)
    BlockchainInterfaceFactory.register_interface(interface=testerchain, force=True)
    yield testerchain


@pytest.fixture(scope='module')
def stake_info(testerchain, test_registry):
    result = test_registry.search(contract_name=STAKE_INFO)[0]
    _stake_info = testerchain.w3.eth.contract(address=result[2], abi=result[3])
    return _stake_info


@pytest.fixture(scope="module")
def ritual_token(testerchain, test_registry):
    result = test_registry.search(contract_name=RITUAL_TOKEN)[0]
    _ritual_token = testerchain.w3.eth.contract(address=result[2], abi=result[3])
    return _ritual_token


@pytest.fixture(scope="module")
def threshold_staking(testerchain, test_registry):
    result = test_registry.search(contract_name=MOCK_STAKING_CONTRACT_NAME)[0]
    _threshold_staking = testerchain.w3.eth.contract(address=result[2], abi=result[3])

    # TODO: Relocate this to pre application setup
    pre_application_agent = ContractAgency.get_agent(
        PREApplicationAgent,
        registry=test_registry,
        provider_uri=TEST_ETH_PROVIDER_URI,
    )

    tx = _threshold_staking.functions.setApplication(
        pre_application_agent.contract_address
    ).transact()
    testerchain.wait_for_receipt(tx)

    return _threshold_staking


@pytest.fixture(scope="module", autouse=True)
def coordinator_agent(testerchain, test_registry):
    """Creates a coordinator agent"""
    coordinator = ContractAgency.get_agent(
        CoordinatorAgent, registry=test_registry, provider_uri=TEST_ETH_PROVIDER_URI
    )
    tx = coordinator.contract.functions.makeInitiationPublic().transact()
    testerchain.wait_for_receipt(tx)
    return coordinator


@pytest.fixture(scope="module")
def global_allow_list(testerchain, test_registry):
    result = test_registry.search(contract_name=GLOBAL_ALLOW_LIST)[0]
    _global_allow_list = testerchain.w3.eth.contract(address=result[2], abi=result[3])
    return _global_allow_list


@pytest.fixture(scope="module")
def staking_providers(
    testerchain, test_registry, threshold_staking, stake_info, coordinator_agent
):
    pre_application_agent = ContractAgency.get_agent(
        PREApplicationAgent,
        registry=test_registry,
        provider_uri=TEST_ETH_PROVIDER_URI,
    )
    blockchain = pre_application_agent.blockchain
    minimum_stake = (
        pre_application_agent.contract.functions.minimumAuthorization().call()
    )

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

        _receipt = pre_application_agent.bond_operator(
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
        tx = stake_info.functions.updateOperator(
            provider_address,
            operator_address,
        ).transact()
        testerchain.wait_for_receipt(tx)

        tx = stake_info.functions.updateAmount(
            provider_address,
            amount,
        ).transact()
        testerchain.wait_for_receipt(tx)

        # track
        staking_providers.append(provider_address)

    yield staking_providers


@pytest.fixture(scope='module')
def manual_operator(testerchain):
    worker_private_key = os.urandom(32).hex()
    address = testerchain.provider.ethereum_tester.add_account(
        worker_private_key,
        password=INSECURE_DEVELOPMENT_PASSWORD
    )

    tx = {'to': address,
          'from': testerchain.etherbase_account,
          'value': Web3.to_wei('1', 'ether')}

    txhash = testerchain.client.w3.eth.send_transaction(tx)
    _receipt = testerchain.wait_for_receipt(txhash)
    yield address


@pytest.fixture(scope="module")
def monkeymodule():
    from _pytest.monkeypatch import MonkeyPatch

    mpatch = MonkeyPatch()
    yield mpatch
    mpatch.undo()


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
