import json
from collections import namedtuple

import pytest
from marshmallow import ValidationError
from packaging.version import parse as parse_version

import nucypher
from nucypher.blockchain.eth.constants import NULL_ADDRESS
from nucypher.policy.conditions.context import USER_ADDRESS_CONTEXT
from nucypher.policy.conditions.exceptions import (
    InvalidConditionLingo,
)
from nucypher.policy.conditions.lingo import (
    AnyField,
    AnyLargeIntegerField,
    ConditionLingo,
    ConditionType,
)
from tests.constants import INT256_MIN, TESTERCHAIN_CHAIN_ID, UINT256_MAX


@pytest.fixture(scope="module")
def lingo_with_condition():
    return {
        "conditionType": ConditionType.TIME.value,
        "returnValueTest": {"value": 0, "comparator": ">"},
        "method": "blocktime",
        "chain": TESTERCHAIN_CHAIN_ID,
    }


@pytest.fixture(scope="module")
def lingo_with_all_condition_types(get_random_checksum_address):
    time_condition = {
        "conditionType": ConditionType.TIME.value,
        "method": "blocktime",
        "chain": TESTERCHAIN_CHAIN_ID,
        "returnValueTest": {"value": 0, "comparator": ">"},
    }
    contract_condition = {
        "conditionType": ConditionType.CONTRACT.value,
        "chain": TESTERCHAIN_CHAIN_ID,
        "method": "isPolicyActive",
        "parameters": [":hrac"],
        "contractAddress": get_random_checksum_address(),
        "functionAbi": {
            "type": "function",
            "name": "isPolicyActive",
            "stateMutability": "view",
            "inputs": [
                {
                    "name": "_policyID",
                    "type": "bytes16",
                    "internalType": "bytes16",
                }
            ],
            "outputs": [{"name": "", "type": "bool", "internalType": "bool"}],
        },
        "returnValueTest": {"comparator": "==", "value": True},
    }
    rpc_condition = {
        # RPC
        "conditionType": ConditionType.RPC.value,
        "chain": TESTERCHAIN_CHAIN_ID,
        "method": "eth_getBalance",
        "parameters": [
            get_random_checksum_address(),
            "latest",
        ],
        "returnValueTest": {
            "comparator": ">=",
            "value": 10000000000000,
        },
    }
    json_api_condition = {
        # JSON API
        "conditionType": ConditionType.JSONAPI.value,
        "endpoint": "https://api.example.com/data",
        "parameters": {
            "ids": "ethereum",
            "vs_currencies": "usd",
        },
        "authorizationToken": ":authToken",
        "query": "$.store.book[0].price",
        "returnValueTest": {
            "comparator": "==",
            "value": 2,
        },
    }
    json_rpc_condition = {
        # JSON RPC
        "conditionType": ConditionType.JSONRPC.value,
        "endpoint": "https://math.example.com/",
        "method": "subtract",
        "params": [42, 23],
        "query": "$.mathresult",
        "returnValueTest": {
            "comparator": "==",
            "value": 19,
        },
    }
    jwt_condition = {
        # JWT
        "conditionType": ConditionType.JWT.value,
        "jwtToken": ":token",
        "publicKey": "-----BEGIN PUBLIC KEY-----\nMFkwEwYHKoZIzj0CAQYIKoZIzj0DAQcDQgAEXHVxB7s5SR7I9cWwry/JkECIReka\nCwG3uOLCYbw5gVzn4dRmwMyYUJFcQWuFSfECRK+uQOOXD0YSEucBq0p5tA==\n-----END PUBLIC KEY-----",
    }
    sequential_condition = {
        "conditionType": ConditionType.SEQUENTIAL.value,
        "conditionVariables": [
            {
                "varName": "timeValue",
                "condition": time_condition,
            },
            {
                "varName": "rpcValue",
                "condition": rpc_condition,
            },
            {
                "varName": "contractValue",
                "condition": contract_condition,
            },
            {
                "varName": "jsonValue",
                "condition": json_api_condition,
            },
            {
                "varName": "jwtValue",
                "condition": jwt_condition,
            },
        ],
    }
    if_then_else_condition = {
        "conditionType": ConditionType.IF_THEN_ELSE.value,
        "ifCondition": rpc_condition,
        "thenCondition": json_api_condition,
        "elseCondition": json_rpc_condition,
    }
    return {
        "version": ConditionLingo.VERSION,
        "condition": {
            "conditionType": ConditionType.COMPOUND.value,
            "operator": "and",
            "operands": [
                contract_condition,
                if_then_else_condition,
                sequential_condition,
                rpc_condition,
                {
                    "conditionType": ConditionType.COMPOUND.value,
                    "operator": "not",
                    "operands": [
                        time_condition,
                    ],
                },
            ],
        },
    }


def test_invalid_condition():
    # no version or condition
    data = dict()
    with pytest.raises(InvalidConditionLingo):
        ConditionLingo.from_dict(data)

    with pytest.raises(InvalidConditionLingo):
        ConditionLingo.from_json(json.dumps(data))

    # no condition
    data = {"version": ConditionLingo.VERSION}
    with pytest.raises(InvalidConditionLingo):
        ConditionLingo.from_dict(data)

    with pytest.raises(InvalidConditionLingo):
        ConditionLingo.from_json(json.dumps(data))

    # invalid condition
    data = {
        "version": ConditionLingo.VERSION,
        "condition": {"dont_mind_me": "nothing_to_see_here"},
    }
    with pytest.raises(InvalidConditionLingo):
        ConditionLingo.from_dict(data)

    with pytest.raises(InvalidConditionLingo):
        ConditionLingo.from_json(json.dumps(data))


def test_invalid_compound_condition():

    # invalid operator
    invalid_operator = {
        "version": ConditionLingo.VERSION,
        "condition": {
            "conditionType": ConditionType.COMPOUND.value,
            "operator": "xTrue",
            "operands": [
                {
                    "conditionType": ConditionType.TIME.value,
                    "returnValueTest": {"value": 0, "comparator": ">"},
                    "method": "blocktime",
                    "chain": TESTERCHAIN_CHAIN_ID,
                },
            ],
        },
    }
    with pytest.raises(InvalidConditionLingo):
        ConditionLingo.from_dict(invalid_operator)

    with pytest.raises(InvalidConditionLingo):
        ConditionLingo.from_json(json.dumps(invalid_operator))

    # < 2 operands for and condition
    invalid_and_operands_lingo = {
        "version": ConditionLingo.VERSION,
        "condition": {
            "conditionType": ConditionType.COMPOUND.value,
            "operator": "and",
            "operands": [
                {
                    "conditionType": ConditionType.TIME.value,
                    "returnValueTest": {"value": 0, "comparator": ">"},
                    "method": "blocktime",
                    "chain": TESTERCHAIN_CHAIN_ID,
                }
            ],
        },
    }
    with pytest.raises(InvalidConditionLingo):
        ConditionLingo.from_dict(invalid_and_operands_lingo)

    with pytest.raises(InvalidConditionLingo):
        ConditionLingo.from_json(json.dumps(invalid_and_operands_lingo))

    # < 2 operands for or condition
    invalid_or_operands_lingo = {
        "version": ConditionLingo.VERSION,
        "condition": {
            "conditionType": ConditionType.COMPOUND.value,
            "operator": "or",
            "operands": [
                {
                    "conditionType": ConditionType.TIME.value,
                    "returnValueTest": {"value": 0, "comparator": ">"},
                    "method": "blocktime",
                    "chain": TESTERCHAIN_CHAIN_ID,
                }
            ],
        },
    }
    with pytest.raises(InvalidConditionLingo):
        ConditionLingo.from_dict(invalid_or_operands_lingo)

    with pytest.raises(InvalidConditionLingo):
        ConditionLingo.from_json(json.dumps(invalid_or_operands_lingo))

    # > 1 operand for `not` condition
    invalid_not_operands_lingo = {
        "version": ConditionLingo.VERSION,
        "condition": {
            "conditionType": ConditionType.COMPOUND.value,
            "operator": "not",
            "operands": [
                {
                    "conditionType": ConditionType.TIME.value,
                    "returnValueTest": {"value": 0, "comparator": ">"},
                    "method": "blocktime",
                    "chain": TESTERCHAIN_CHAIN_ID,
                },
                {
                    "conditionType": ConditionType.TIME.value,
                    "returnValueTest": {"value": 99999999999999999, "comparator": "<"},
                    "method": "blocktime",
                    "chain": TESTERCHAIN_CHAIN_ID,
                },
            ],
        },
    }
    with pytest.raises(InvalidConditionLingo):
        ConditionLingo.from_dict(invalid_not_operands_lingo)

    with pytest.raises(InvalidConditionLingo):
        ConditionLingo.from_json(json.dumps(invalid_not_operands_lingo))


@pytest.mark.parametrize("case", ["major", "minor", "patch"])
def test_invalid_condition_version(case):
    # version in the future
    current_version = parse_version(ConditionLingo.VERSION)
    major = current_version.major
    minor = current_version.minor
    patch = current_version.micro
    if case == "major":
        major += 1
    elif case == "minor":
        minor += 1
    else:
        patch += 1

    newer_version_string = f"{major}.{minor}.{patch}"
    lingo_dict = {
        "version": newer_version_string,
        "condition": {
            "conditionType": ConditionType.TIME.value,
            "returnValueTest": {"value": 0, "comparator": ">"},
            "method": "blocktime",
            "chain": TESTERCHAIN_CHAIN_ID,
        },
    }
    if case == "major":
        # exception should be thrown since incompatible:
        with pytest.raises(InvalidConditionLingo):
            ConditionLingo.from_dict(lingo_dict)

        with pytest.raises(InvalidConditionLingo):
            ConditionLingo.from_json(json.dumps(lingo_dict))
    else:
        # no exception thrown
        _ = ConditionLingo.from_dict(lingo_dict)
        _ = ConditionLingo.from_json(json.dumps(lingo_dict))


def test_condition_lingo_to_from_dict(lingo_with_all_condition_types):
    clingo = ConditionLingo.from_dict(lingo_with_all_condition_types)
    clingo_dict = clingo.to_dict()
    assert clingo_dict == lingo_with_all_condition_types


def test_condition_lingo_to_from_json(lingo_with_all_condition_types):
    # A bit more convoluted because fields aren't
    # necessarily ordered - so string comparison is tricky
    clingo_from_dict = ConditionLingo.from_dict(lingo_with_all_condition_types)
    lingo_json = clingo_from_dict.to_json()

    clingo_from_json = ConditionLingo.from_json(lingo_json)
    assert clingo_from_json.to_dict() == lingo_with_all_condition_types


def test_compound_condition_lingo_repr(lingo_with_all_condition_types):
    clingo = ConditionLingo.from_dict(lingo_with_all_condition_types)
    clingo_string = f"{clingo}"
    assert f"{clingo.__class__.__name__}" in clingo_string
    assert f"version={ConditionLingo.VERSION}" in clingo_string
    assert f"id={clingo.id}" in clingo_string
    assert f"size={len(bytes(clingo))}" in clingo_string


def test_lingo_parameter_int_type_preservation(custom_abi_with_multiple_parameters, mocker):
    mocker.patch.dict(
        nucypher.policy.conditions.context._DIRECTIVES,
        {USER_ADDRESS_CONTEXT: lambda: NULL_ADDRESS},
    )
    clingo_json = json.dumps(
        {
            "version": ConditionLingo.VERSION,
            "condition": json.loads(
                custom_abi_with_multiple_parameters  # fixture is already a json string
            ),
        }
    )

    clingo = ConditionLingo.from_json(clingo_json)
    conditions = clingo.to_dict()
    assert conditions["condition"]["parameters"][2] == 4


def test_lingo_resolves_condition_type(lingo_with_condition):
    for condition_type in ConditionType.values():
        lingo_with_condition["conditionType"] = condition_type
        ConditionLingo.resolve_condition_class(lingo_with_condition)


def test_lingo_rejects_invalid_condition_type(lingo_with_condition):
    for condition_type in ["invalid", "", None]:
        lingo_with_condition["conditionType"] = condition_type
        with pytest.raises(InvalidConditionLingo):
            ConditionLingo.resolve_condition_class(lingo_with_condition)


def test_lingo_data(conditions_test_data):
    for name, condition_dict in conditions_test_data.items():
        condition_class = ConditionLingo.resolve_condition_class(condition_dict)
        _ = condition_class.from_dict(condition_dict)


@pytest.mark.parametrize(
    "value",
    [
        1231323123132,
        2121.23211,
        False,
        '"foo"',  # string
        "5555555555",  # example of a number that was a string and should remain a string
        ":userAddress",  # context variable
        "0xaDD9D957170dF6F33982001E4c22eCCdd5539118",  # string
        "0x1234",  # hex string
        125,  # int
        -123456789,  # negative int
        1.223,  # float
        True,  # bool
        [1, 1.2314, False, "love"],  # list of different types
        ["a", "b", "c"],  # list
        [True, False],  # list of bools
        {"name": "John", "age": 22},  # dict
        namedtuple("MyStruct", ["field1", "field2"])(1, "a"),
        [True, 2, 6.5, "0x123"],
    ],
)
def test_any_field_various_types(value):
    field = AnyField()

    deserialized_value = field.deserialize(value)
    serialized_value = field._serialize(deserialized_value, attr=None, obj=None)

    assert deserialized_value == serialized_value
    assert deserialized_value == value


@pytest.mark.parametrize(
    "integer_value",
    [
        UINT256_MAX,
        INT256_MIN,
        123132312,  # safe int
        -1231231,  # safe negative int
    ],
)
def test_any_field_integer_str_and_no_str_conversion(integer_value):
    field = AnyField()

    deserialized_raw_integer = field.deserialize(value=integer_value)
    deserialized_big_int_string = field.deserialize(value=f"{integer_value}n")
    assert deserialized_raw_integer == deserialized_big_int_string

    assert (
        field._serialize(deserialized_raw_integer, attr=None, obj=None) == integer_value
    )
    assert (
        field._serialize(deserialized_big_int_string, attr=None, obj=None)
        == integer_value
    )


def test_any_field_nested_integer():
    field = AnyField()

    regular_number = 12341231

    parameters = [
        f"{UINT256_MAX}n",
        {"a": [f"{INT256_MIN}n", "my_string_value", "0xdeadbeef"], "b": regular_number},
    ]
    # quoted numbers get unquoted after deserialization
    expected_parameters = [
        UINT256_MAX,
        {"a": [INT256_MIN, "my_string_value", "0xdeadbeef"], "b": regular_number},
    ]

    deserialized_parameters = field.deserialize(value=parameters)
    assert deserialized_parameters == expected_parameters


@pytest.mark.parametrize(
    "json_value, expected_deserialized_value",
    [
        (123132312, 123132312),  # safe int
        (-1231231, -1231231),  # safe negative int
        (f"{UINT256_MAX}n", UINT256_MAX),
        (f"{INT256_MIN}n", INT256_MIN),
        (f"{UINT256_MAX*2}n", UINT256_MAX * 2),  # larger than uint256 max
        (f"{INT256_MIN*2}n", INT256_MIN * 2),  # smaller than in256 min
        # expected failures
        ("Totally a number", None),
        ("Totally a number that ends with n", None),
        ("fallen", None),
    ],
)
def test_any_large_integer_field(json_value, expected_deserialized_value):
    field = AnyLargeIntegerField()

    if expected_deserialized_value is not None:
        assert field.deserialize(json_value) == expected_deserialized_value
    else:
        # expected to fail
        with pytest.raises(ValidationError, match="Not a valid integer."):
            _ = field.deserialize(json_value)
