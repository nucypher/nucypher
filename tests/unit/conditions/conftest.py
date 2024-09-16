import json

import pytest

from nucypher.policy.conditions.base import AccessControlCondition
from nucypher.policy.conditions.context import USER_ADDRESS_CONTEXT
from nucypher.policy.conditions.evm import ContractCondition
from nucypher.policy.conditions.lingo import (
    AndCompoundCondition,
    ConditionLingo,
    OrCompoundCondition,
    ReturnValueTest,
)
from tests.constants import TESTERCHAIN_CHAIN_ID


@pytest.fixture()
def compound_lingo(
    erc721_evm_condition, time_condition, rpc_condition, erc20_evm_condition
):
    """does not depend on contract deployments"""
    lingo = ConditionLingo(
        condition=OrCompoundCondition(
            operands=[
                erc721_evm_condition,
                time_condition,
                AndCompoundCondition(operands=[rpc_condition, erc20_evm_condition]),
            ]
        )
    )
    return lingo


@pytest.fixture()
def erc1155_balance_condition_data(conditions_test_data):
    data = json.dumps(conditions_test_data['ERC1155_balance'])
    return data


@pytest.fixture()
def erc1155_balance_condition(erc1155_balance_condition_data):
    data = erc1155_balance_condition_data
    condition = ContractCondition.from_json(data)
    return condition


@pytest.fixture()
def erc20_balance_condition_data(conditions_test_data):
    data = json.dumps(conditions_test_data['ERC20_balance'])
    return data


@pytest.fixture()
def erc20_balance_condition(erc20_balance_condition_data):
    data = erc20_balance_condition_data
    condition = ContractCondition.from_json(data)
    return condition


@pytest.fixture()
def t_staking_data(conditions_test_data):
    return json.dumps(conditions_test_data["TStaking"])


@pytest.fixture()
def custom_abi_with_multiple_parameters(conditions_test_data):
    return json.dumps(conditions_test_data["customABIMultipleParameters"])


@pytest.fixture
def erc20_evm_condition(test_registry):
    condition = ContractCondition(
        contract_address="0xaDD9D957170dF6F33982001E4c22eCCdd5539118",
        method="balanceOf",
        standard_contract_type="ERC20",
        chain=TESTERCHAIN_CHAIN_ID,
        return_value_test=ReturnValueTest("==", 0),
        parameters=[
            USER_ADDRESS_CONTEXT,
        ],
    )
    return condition


@pytest.fixture
def erc721_evm_condition(test_registry):
    condition = ContractCondition(
        contract_address="0xaDD9D957170dF6F33982001E4c22eCCdd5539118",
        method="ownerOf",
        standard_contract_type="ERC721",
        chain=TESTERCHAIN_CHAIN_ID,
        return_value_test=ReturnValueTest("==", ":userAddress"),
        parameters=[
            5954,
        ]
    )
    return condition


@pytest.fixture(scope="function")
def mock_skip_schema_validation(mocker):
    mocker.patch.object(AccessControlCondition.Schema, "validate", return_value=None)
