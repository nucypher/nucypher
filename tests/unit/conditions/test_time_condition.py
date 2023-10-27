import pytest

from nucypher.policy.conditions.exceptions import InvalidCondition
from nucypher.policy.conditions.lingo import ConditionType, ReturnValueTest
from nucypher.policy.conditions.time import TimeCondition
from tests.constants import TESTERCHAIN_CHAIN_ID


def test_invalid_time_condition():
    # invalid condition type
    with pytest.raises(InvalidCondition, match=ConditionType.TIME.value):
        _ = TimeCondition(
            condition_type=ConditionType.COMPOUND.value,
            return_value_test=ReturnValueTest(">", 0),
            chain=TESTERCHAIN_CHAIN_ID,
            method=TimeCondition.METHOD,
        )

    # invalid method
    with pytest.raises(InvalidCondition):
        _ = TimeCondition(
            return_value_test=ReturnValueTest(">", 0),
            chain=TESTERCHAIN_CHAIN_ID,
            method="time_after_time",
        )


def test_time_condition_schema_validation(time_condition):
    condition_dict = time_condition.to_dict()

    # no issues here
    TimeCondition.validate(condition_dict)

    # no issues with optional name
    condition_dict["name"] = "my_time_machine"
    TimeCondition.validate(condition_dict)

    with pytest.raises(InvalidCondition):
        # no method
        condition_dict = time_condition.to_dict()
        del condition_dict["method"]
        TimeCondition.validate(condition_dict)

    with pytest.raises(InvalidCondition):
        # no returnValueTest defined
        condition_dict = time_condition.to_dict()
        del condition_dict["returnValueTest"]
        TimeCondition.validate(condition_dict)
