import json

import pytest
from packaging.version import parse as parse_version

import nucypher
from nucypher.blockchain.eth.constants import NULL_ADDRESS
from nucypher.policy.conditions.context import USER_ADDRESS_CONTEXT
from nucypher.policy.conditions.exceptions import InvalidConditionLingo
from nucypher.policy.conditions.lingo import ConditionLingo
from tests.constants import TESTERCHAIN_CHAIN_ID


@pytest.fixture(scope='module')
def lingo():
    return {
        "version": ConditionLingo.VERSION,
        "condition": {
            "operator": "and",
            "operands": [
                {
                    "returnValueTest": {"value": 0, "comparator": ">"},
                    "method": "blocktime",
                    "chain": TESTERCHAIN_CHAIN_ID,
                },
                {
                    "returnValueTest": {"value": 99999999999999999, "comparator": "<"},
                    "method": "blocktime",
                    "chain": TESTERCHAIN_CHAIN_ID,
                },
            ],
        },
    }


def test_invalid_condition(lingo):
    # no version or condition
    with pytest.raises(InvalidConditionLingo):
        ConditionLingo.from_dict({})

    # no condition
    with pytest.raises(InvalidConditionLingo):
        ConditionLingo.from_dict({"version": ConditionLingo.VERSION})

    # invalid condition
    with pytest.raises(InvalidConditionLingo):
        ConditionLingo.from_dict(
            {
                "version": ConditionLingo.VERSION,
                "condition": {"dont_mind_me": "nothing_to_see_here"},
            }
        )

    # < 2 operands for and condition
    invalid_operator_position_lingo = {
        "version": ConditionLingo.VERSION,
        "condition": {
            "operator": "and",
            "operands": [
                {
                    "returnValueTest": {"value": 0, "comparator": ">"},
                    "method": "blocktime",
                    "chain": TESTERCHAIN_CHAIN_ID,
                }
            ],
        },
    }
    with pytest.raises(InvalidConditionLingo):
        ConditionLingo.from_dict(invalid_operator_position_lingo)


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
            "returnValueTest": {"value": 0, "comparator": ">"},
            "method": "blocktime",
            "chain": TESTERCHAIN_CHAIN_ID,
        },
    }
    if case == "major":
        # exception should be thrown since incompatible:
        with pytest.raises(InvalidConditionLingo):
            ConditionLingo.from_dict(lingo_dict)
    else:
        # no exception thrown
        ConditionLingo.from_dict(lingo_dict)


def test_condition_lingo_to_from_dict(lingo):
    clingo = ConditionLingo.from_dict(lingo)
    clingo_dict = clingo.to_dict()
    assert clingo_dict == lingo


def test_condition_lingo_repr(lingo):
    clingo = ConditionLingo.from_dict(lingo)
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
    clingo = ConditionLingo.from_dict(
        {
            "version": ConditionLingo.VERSION,
            "condition": json.loads(
                custom_abi_with_multiple_parameters
            ),  # TODO fix this
        }
    )
    conditions = clingo.to_dict()
    assert conditions["condition"]["parameters"][2] == 4
