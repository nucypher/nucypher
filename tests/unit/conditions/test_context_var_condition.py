import pytest

from nucypher.policy.conditions.exceptions import (
    InvalidCondition,
    InvalidConditionLingo,
)
from nucypher.policy.conditions.lingo import ConditionType, ReturnValueTest
from nucypher.policy.conditions.var import ContextVariableCondition


def test_invalid_context_variable_condition():
    # invalid condition type
    with pytest.raises(InvalidCondition, match=ConditionType.CONTEXT_VARIABLE.value):
        _ = ContextVariableCondition(
            condition_type=ConditionType.TIME.value,
            context_variable=":myContextVar",
            return_value_test=ReturnValueTest(comparator="==", value=0),
        )

    # not context var
    with pytest.raises(InvalidCondition, match="Invalid value for context variable"):
        _ = ContextVariableCondition(
            context_variable="noColon",
            return_value_test=ReturnValueTest(comparator="==", value=0),
        )

    # no context var
    with pytest.raises(InvalidCondition, match="Missing data for required field"):
        _ = ContextVariableCondition(
            context_variable=None,
            return_value_test=ReturnValueTest(comparator="==", value=0),
        )

    # no return value test var
    with pytest.raises(InvalidCondition, match="Missing data for required field"):
        _ = ContextVariableCondition(
            context_variable=":userAddress", return_value_test=None
        )


def test_context_variable_condition_initialization():
    context_variable = ":contextVar"

    condition = ContextVariableCondition(
        context_variable=context_variable,
        return_value_test=ReturnValueTest("==", 19),
    )

    assert condition.context_variable == context_variable
    assert condition.return_value_test.comparator == "=="
    assert condition.return_value_test.value == 19
    assert condition.return_value_test.eval(19)


def test_context_variable_condition_schema_validation():
    condition = ContextVariableCondition(
        context_variable=":contextVar",
        return_value_test=ReturnValueTest("==", 20),
    )
    condition_dict = condition.to_dict()

    # no issues here
    ContextVariableCondition.from_dict(condition_dict)

    # no issues with optional name
    condition_dict["name"] = "my_context_var_condition"
    ContextVariableCondition.from_dict(condition_dict)

    with pytest.raises(InvalidConditionLingo):
        # no context var defined
        condition_dict = condition.to_dict()
        del condition_dict["contextVariable"]
        ContextVariableCondition.from_dict(condition_dict)

    with pytest.raises(InvalidConditionLingo):
        # no return value test defined
        condition_dict = condition.to_dict()
        del condition_dict["returnValueTest"]
        ContextVariableCondition.from_dict(condition_dict)


def test_context_variable_condition_repr(rpc_condition):
    condition = ContextVariableCondition(
        context_variable=":contextVar",
        return_value_test=ReturnValueTest("==", 19),
    )
    condition_str = str(condition)
    assert condition.__class__.__name__ in condition_str
    assert "contextVariable=:contextVar" in condition_str


def test_context_variable_condition_verify(mocker, condition_provider_manager):
    condition = ContextVariableCondition(
        context_variable=":contextVar",
        return_value_test=ReturnValueTest("==", 19),
    )
    value = 19
    context = {":contextVar": value}
    success, result = condition.verify(providers=condition_provider_manager, **context)
    assert success is True
    assert result == value

    value = "'When the debate is lost, slander becomes the tool of the loser'"
    context = {":contextVar": value}
    success, result = condition.verify(providers=condition_provider_manager, **context)
    assert success is False
    assert result == value


def test_context_variable_condition_verify_list(mocker, condition_provider_manager):
    expected = [1, True, "test"]
    condition = ContextVariableCondition(
        context_variable=":contextVar",
        return_value_test=ReturnValueTest("==", expected),
    )
    context = {":contextVar": expected}
    success, result = condition.verify(providers=condition_provider_manager, **context)
    assert success is True
    assert result == expected

    value = [1, "here comes the 2 to the 3 to the 4"]
    context = {":contextVar": value}
    success, result = condition.verify(providers=condition_provider_manager, **context)
    assert success is False
    assert result == value
