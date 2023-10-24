import copy
import json
from typing import Any, Dict, Sequence

import pytest

from nucypher.policy.conditions.evm import ContractCondition
from nucypher.policy.conditions.exceptions import InvalidCondition

CONTRACT_CONDITION = {
    "conditionType": "contract",
    "contractAddress": "0x01B67b1194C75264d06F808A921228a95C765dd7",
    "method": "isSubscribedToToken",
    "parameters": [":userAddress", "subscriptionCode", 4],
    "functionAbi": {
        "inputs": [
            {"internalType": "address", "name": "subscriber", "type": "address"},
            {"internalType": "bytes32", "name": "subscriptionCode", "type": "bytes32"},
            {"internalType": "uint256", "name": "tokenId", "type": "uint256"},
        ],
        "name": "isSubscribedToToken",
        "outputs": [{"internalType": "bool", "name": "valid", "type": "bool"}],
        "stateMutability": "view",
        "type": "function",
        "constant": True,
    },
    "chain": 137,
    "returnValueTest": {"comparator": "==", "value": True},
}


@pytest.fixture(scope="function")
def contract_condition_dict():
    return copy.deepcopy(CONTRACT_CONDITION)


def _replace_abi_outputs(condition_json: Dict, output_type: str, output_value: Any):
    # modify outputs type
    condition_json["functionAbi"]["outputs"][0]["internalType"] = output_type
    condition_json["functionAbi"]["outputs"][0]["type"] = output_type

    # modify return value test
    condition_json["returnValueTest"]["value"] = output_value


def test_abi_bool_output(contract_condition_dict):
    # default - no changes to json
    contract_condition = ContractCondition.from_json(
        json.dumps(contract_condition_dict)
    )
    assert isinstance(contract_condition.return_value_test.value, bool)

    # invalid type fails
    with pytest.raises(InvalidCondition, match="Invalid return value comparison type"):
        contract_condition_dict["returnValueTest"]["value"] = 23
        ContractCondition.from_json(json.dumps(contract_condition_dict))


def test_abi_uint_output(contract_condition_dict):
    _replace_abi_outputs(contract_condition_dict, "uint256", 123456789)
    contract_condition = ContractCondition.from_json(
        json.dumps(contract_condition_dict)
    )
    assert isinstance(contract_condition.return_value_test.value, int)

    # invalid type fails
    with pytest.raises(InvalidCondition, match="Invalid return value comparison type"):
        contract_condition_dict["returnValueTest"]["value"] = True
        ContractCondition.from_json(json.dumps(contract_condition_dict))


def test_abi_int_output(contract_condition_dict):
    _replace_abi_outputs(contract_condition_dict, "int256", -123456789)
    contract_condition = ContractCondition.from_json(
        json.dumps(contract_condition_dict)
    )
    assert isinstance(contract_condition.return_value_test.value, int)

    # invalid type fails
    with pytest.raises(InvalidCondition, match="Invalid return value comparison type"):
        contract_condition_dict["returnValueTest"]["value"] = [1, 2, 3]
        ContractCondition.from_json(json.dumps(contract_condition_dict))


def test_abi_address_output(contract_condition_dict, get_random_checksum_address):
    _replace_abi_outputs(
        contract_condition_dict, "address", get_random_checksum_address()
    )
    contract_condition = ContractCondition.from_json(
        json.dumps(contract_condition_dict)
    )
    assert isinstance(contract_condition.return_value_test.value, str)

    # invalid type fails
    with pytest.raises(InvalidCondition, match="Invalid return value comparison type"):
        contract_condition_dict["returnValueTest"]["value"] = 1.25
        ContractCondition.from_json(json.dumps(contract_condition_dict))


def test_abi_tuple_output(contract_condition_dict):
    contract_condition_dict["functionAbi"]["outputs"] = [
        {"internalType": "uint96", "name": "tStake", "type": "uint96"},
        {"internalType": "uint96", "name": "keepInTStake", "type": "uint96"},
        {"internalType": "uint96", "name": "nuInTStake", "type": "uint96"},
    ]
    contract_condition_dict["returnValueTest"]["value"] = [1, 2, 3]
    contract_condition = ContractCondition.from_json(
        json.dumps(contract_condition_dict)
    )
    assert isinstance(contract_condition.return_value_test.value, Sequence)

    # 1. invalid type
    with pytest.raises(InvalidCondition, match="Invalid return value comparison type"):
        contract_condition_dict["returnValueTest"]["value"] = 1
        ContractCondition.from_json(json.dumps(contract_condition_dict))

    # 2. invalid number of values
    with pytest.raises(InvalidCondition, match="Invalid return value comparison type"):
        contract_condition_dict["returnValueTest"]["value"] = [1, 2]
        ContractCondition.from_json(json.dumps(contract_condition_dict))

    # 3a. Unmatched type
    with pytest.raises(InvalidCondition, match="Invalid return value comparison type"):
        contract_condition_dict["returnValueTest"]["value"] = [True, 2, 3]
        ContractCondition.from_json(json.dumps(contract_condition_dict))

    # 3b. Unmatched type
    with pytest.raises(InvalidCondition, match="Invalid return value comparison type"):
        contract_condition_dict["returnValueTest"]["value"] = [1, False, 3]
        ContractCondition.from_json(json.dumps(contract_condition_dict))

    # 3c. Unmatched type
    with pytest.raises(InvalidCondition, match="Invalid return value comparison type"):
        contract_condition_dict["returnValueTest"]["value"] = [1, 2, 3.14159]
        ContractCondition.from_json(json.dumps(contract_condition_dict))


def test_abi_tuple_output_with_index(
    contract_condition_dict, get_random_checksum_address
):
    contract_condition_dict["functionAbi"]["outputs"] = [
        {"internalType": "uint96", "name": "tStake", "type": "uint96"},
        {"internalType": "uint96", "name": "hasKeep", "type": "bool"},
        {"internalType": "uint96", "name": "nuAddress", "type": "address"},
    ]

    # without index
    contract_condition_dict["returnValueTest"]["value"] = [
        1,
        True,
        get_random_checksum_address(),
    ]
    contract_condition = ContractCondition.from_json(
        json.dumps(contract_condition_dict)
    )
    assert isinstance(contract_condition.return_value_test.value, Sequence)

    # index 0
    contract_condition_dict["returnValueTest"]["index"] = 0
    contract_condition_dict["returnValueTest"]["value"] = 1
    contract_condition = ContractCondition.from_json(
        json.dumps(contract_condition_dict)
    )
    assert isinstance(contract_condition.return_value_test.value, int)

    # index 1
    contract_condition_dict["returnValueTest"]["index"] = 1
    contract_condition_dict["returnValueTest"]["value"] = True
    contract_condition = ContractCondition.from_json(
        json.dumps(contract_condition_dict)
    )
    assert isinstance(contract_condition.return_value_test.value, bool)

    # index 2
    contract_condition_dict["returnValueTest"]["index"] = 2
    contract_condition_dict["returnValueTest"]["value"] = get_random_checksum_address()
    contract_condition = ContractCondition.from_json(
        json.dumps(contract_condition_dict)
    )
    assert isinstance(contract_condition.return_value_test.value, str)

    # invalid type at index
    with pytest.raises(InvalidCondition, match="Invalid return value comparison type"):
        contract_condition_dict["returnValueTest"]["index"] = 0
        contract_condition_dict["returnValueTest"][
            "value"
        ] = get_random_checksum_address()
        ContractCondition.from_json(json.dumps(contract_condition_dict))
