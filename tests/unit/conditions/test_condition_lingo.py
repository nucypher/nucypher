import pytest
from marshmallow import ValidationError

import nucypher
from nucypher.blockchain.eth.constants import NULL_ADDRESS
from nucypher.policy.conditions.context import USER_ADDRESS_CONTEXT
from nucypher.policy.conditions.exceptions import InvalidConditionLingo
from nucypher.policy.conditions.lingo import ConditionLingo
from tests.constants import TESTERCHAIN_CHAIN_ID


@pytest.fixture(scope='module')
def lingo():
    return {
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
    }


def test_invalid_condition():
    with pytest.raises(InvalidConditionLingo):
        ConditionLingo.from_dict({})

    with pytest.raises(InvalidConditionLingo):
        ConditionLingo.from_dict({"dont_mind_me": "nothing_to_see_here"})

    # < 2 operands for and condition
    invalid_operator_position_lingo = {
        "operator": "and",
        "operands": [
            {
                "returnValueTest": {"value": 0, "comparator": ">"},
                "method": "blocktime",
                "chain": TESTERCHAIN_CHAIN_ID,
            }
        ],
    }
    # TODO - see if I can customize this error
    with pytest.raises(ValidationError):
        ConditionLingo.from_dict(invalid_operator_position_lingo)


def test_condition_lingo_to_from_dict(lingo):
    clingo = ConditionLingo.from_dict(lingo)
    clingo_dict = clingo.to_dict()
    assert clingo_dict == lingo


def test_condition_lingo_repr(lingo):
    clingo = ConditionLingo.from_dict(lingo)
    clingo_string = f"{clingo}"
    assert f"{clingo.__class__.__name__}" in clingo_string
    assert f"id={clingo.id}" in clingo_string
    assert f"size={len(bytes(clingo))}" in clingo_string


def test_lingo_parameter_int_type_preservation(custom_abi_with_multiple_parameters, mocker):
    mocker.patch.dict(
        nucypher.policy.conditions.context._DIRECTIVES,
        {USER_ADDRESS_CONTEXT: lambda: NULL_ADDRESS},
    )
    clingo = ConditionLingo.from_dict(custom_abi_with_multiple_parameters)
    conditions = clingo.to_dict()
    assert conditions["parameters"][2] == 4
