import pytest

import nucypher
from nucypher.blockchain.eth.constants import NULL_ADDRESS
from nucypher.policy.conditions.context import USER_ADDRESS_CONTEXT
from nucypher.policy.conditions.lingo import ConditionLingo

CONDITIONS = [
        {
            "returnValueTest": {"value": 0, "comparator": ">"},
            "method": "timelock"
        },
        {"operator": "and"},
        {
            "returnValueTest": {"value": 99999999999999999, "comparator": "<"},
            "method": "timelock",
        },
    ]


def test_invalid_condition():
    with pytest.raises(Exception):
        ConditionLingo.from_list([{}])

    with pytest.raises(Exception):
        ConditionLingo.from_list([{"dont_mind_me": "nothing_to_see_here"}])


def test_condition_lingo_to_from_list():
    clingo = ConditionLingo.from_list(CONDITIONS)
    clingo_list = clingo.to_list()
    assert clingo_list == CONDITIONS


def test_compound_condition():
    clingo = ConditionLingo.from_list(CONDITIONS)
    assert clingo.eval()


def test_condition_lingo_repr():
    clingo = ConditionLingo.from_list(CONDITIONS)
    clingo_string = f"{clingo}"
    assert f"{clingo.__class__.__name__}" in clingo_string
    assert f"id={clingo.id}" in clingo_string
    assert f"size={len(bytes(clingo))}" in clingo_string


def test_condition_lingo_bug(condition_bug_data, condition_providers, mocker):
    mocker.patch.dict(
        nucypher.policy.conditions.context._DIRECTIVES,
        {USER_ADDRESS_CONTEXT: lambda: NULL_ADDRESS},
    )
    clingo = ConditionLingo.from_list([condition_bug_data])
    conditions = clingo.to_list()
    assert conditions[0]["parameters"][2] == 4
