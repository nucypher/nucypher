from pathlib import Path

import pytest

import nucypher
from nucypher.blockchain.eth.agents import (
    ContractAgency,
    NucypherTokenAgent,
    SubscriptionManagerAgent,
)
from nucypher.blockchain.eth.signers.software import Web3Signer
from nucypher.blockchain.eth.sol.compile.compile import multiversion_compile
from nucypher.blockchain.eth.sol.compile.types import SourceBundle
from nucypher.crypto.powers import TransactingPower
from nucypher.policy.conditions.context import USER_ADDRESS_CONTEXT
from nucypher.policy.conditions.evm import ContractCondition
from nucypher.policy.conditions.lingo import AND, OR, ConditionLingo, ReturnValueTest
from tests.constants import TESTERCHAIN_CHAIN_ID


@pytest.fixture()
def condition_providers(testerchain):
    providers = {testerchain.client.chain_id: testerchain.provider}
    return providers


@pytest.fixture(autouse=True)
def mock_condition_blockchains(mocker):
    """adds testerchain's chain ID to permitted conditional chains"""
    mocker.patch.object(
        nucypher.policy.conditions.evm, "_CONDITION_CHAINS", tuple([TESTERCHAIN_CHAIN_ID])
    )


@pytest.fixture()
def compound_lingo(erc721_evm_condition_balanceof,
                   timelock_condition,
                   rpc_condition,
                   erc20_evm_condition_balanceof):
    """depends on contract deployments"""
    lingo = ConditionLingo(
        conditions=[
            erc721_evm_condition_balanceof,
            OR,
            timelock_condition,
            OR,
            rpc_condition,
            AND,
            erc20_evm_condition_balanceof,
        ]
    )
    return lingo


@pytest.fixture()
def erc20_evm_condition_balanceof(test_registry, agency):
    token = ContractAgency.get_agent(NucypherTokenAgent, registry=test_registry)
    condition = ContractCondition(
        contract_address=token.contract.address,
        method="balanceOf",
        standard_contract_type="ERC20",
        chain=TESTERCHAIN_CHAIN_ID,
        return_value_test=ReturnValueTest("==", 0),
        parameters=[USER_ADDRESS_CONTEXT],
    )
    return condition


@pytest.fixture
def erc721_contract(testerchain, test_registry):
    solidity_root = Path(__file__).parent / "contracts"
    source_bundle = SourceBundle(base_path=solidity_root)
    compiled_contracts = multiversion_compile([source_bundle], True)
    testerchain._raw_contract_cache = compiled_contracts

    origin, *everybody_else = testerchain.client.accounts
    transacting_power = TransactingPower(
        account=origin, signer=Web3Signer(testerchain.client)
    )
    contract, receipt = testerchain.deploy_contract(
        transacting_power=transacting_power,
        registry=test_registry,
        contract_name="ConditionNFT",
    )
    # mint an NFT with tokenId = 1
    tx = contract.functions.mint(origin, 1).transact({"from": origin})
    testerchain.wait_for_receipt(tx)

    return contract


@pytest.fixture
def erc721_evm_condition_owner(erc721_contract):
    condition = ContractCondition(
        contract_address=erc721_contract.address,
        method="ownerOf",
        standard_contract_type="ERC721",
        chain=TESTERCHAIN_CHAIN_ID,
        return_value_test=ReturnValueTest("==", ":userAddress"),
        parameters=[
            ":tokenId",
        ],
    )
    return condition


@pytest.fixture
def erc721_evm_condition_balanceof(erc721_contract):
    condition = ContractCondition(
        contract_address=erc721_contract.address,
        method="balanceOf",
        standard_contract_type="ERC721",
        chain=TESTERCHAIN_CHAIN_ID,
        return_value_test=ReturnValueTest(">", 0),
        parameters=[
            ":userAddress",
        ],
    )

    return condition


@pytest.fixture
def subscription_manager_get_policy_zeroized_policy_struct_condition(
    test_registry, agency
):
    subscription_manager = ContractAgency.get_agent(
        SubscriptionManagerAgent, registry=test_registry
    )
    condition = ContractCondition(
        contract_address=subscription_manager.contract.address,
        function_abi=subscription_manager.contract.get_function_by_name("getPolicy").abi,
        method="getPolicy",
        chain=TESTERCHAIN_CHAIN_ID,
        return_value_test=ReturnValueTest("==", ":expectedPolicyStruct"),
        parameters=[":hrac"],
    )
    return condition


@pytest.fixture
def subscription_manager_is_active_policy_condition(test_registry, agency):
    subscription_manager = ContractAgency.get_agent(
        SubscriptionManagerAgent,
        registry=test_registry
    )
    condition = ContractCondition(
        contract_address=subscription_manager.contract.address,
        function_abi=subscription_manager.contract.get_function_by_name("isPolicyActive").abi,
        method="isPolicyActive",
        chain=TESTERCHAIN_CHAIN_ID,
        return_value_test=ReturnValueTest("==", True),
        parameters=[":hrac"],
    )
    return condition


@pytest.fixture
def custom_context_variable_erc20_condition(
    test_registry, agency, testerchain, mock_condition_blockchains
):
    token = ContractAgency.get_agent(NucypherTokenAgent, registry=test_registry)
    condition = ContractCondition(
        contract_address=token.contract.address,
        method="balanceOf",
        standard_contract_type="ERC20",
        chain=TESTERCHAIN_CHAIN_ID,
        return_value_test=ReturnValueTest("==", 0),
        parameters=[":addressToUse"],
    )
    return condition
