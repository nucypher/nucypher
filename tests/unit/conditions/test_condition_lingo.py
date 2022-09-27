from nucypher.policy.conditions.lingo import ConditionLingo


def test_compound_condition_timelock():
    conditions = [
        {'returnValueTest': {'value': '0', 'comparator': '>'}, 'method': 'timelock'},
        {'operator': 'and'},
        {'returnValueTest': {'value': '99999999999999999', 'comparator': '<'}, 'method': 'timelock'},
    ]

    clingo = ConditionLingo.from_list(conditions)
    assert clingo.eval()
