import pytest

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


def test_compound_condition_timelock():
    clingo = ConditionLingo.from_list(CONDITIONS)
    assert clingo.eval()


def test_condition_lingo_repr():
    clingo = ConditionLingo.from_list(CONDITIONS)
    clingo_string = f"{clingo}"
    assert f"{clingo.__class__.__name__}" in clingo_string
    assert f"id={clingo.id}" in clingo_string
    assert f"size={len(bytes(clingo))}" in clingo_string
