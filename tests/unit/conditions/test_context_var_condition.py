import pytest

from nucypher.policy.conditions.exceptions import (
    InvalidCondition,
    InvalidConditionLingo,
)
from nucypher.policy.conditions.lingo import ConditionType, ReturnValueTest
from nucypher.policy.conditions.var import ContextVarCondition


def test_invalid_context_var_condition():
    # invalid condition type
    with pytest.raises(InvalidCondition, match=ConditionType.CONTEXT_VAR.value):
        _ = ContextVarCondition(
            condition_type=ConditionType.TIME.value,
            context_var=":myContextVar",
            return_value_test=ReturnValueTest(comparator="==", value=0),
        )

    # not context var
    with pytest.raises(InvalidCondition, match="Invalid value for context variable"):
        _ = ContextVarCondition(
            context_var="noColon",
            return_value_test=ReturnValueTest(comparator="==", value=0),
        )

    # no context var
    with pytest.raises(InvalidCondition, match="Missing data for required field"):
        _ = ContextVarCondition(
            context_var=None,
            return_value_test=ReturnValueTest(comparator="==", value=0),
        )

    # no return value test var
    with pytest.raises(InvalidCondition, match="Missing data for required field"):
        _ = ContextVarCondition(context_var=":userAddress", return_value_test=None)


def test_context_var_condition_initialization():
    context_variable = ":contextVar"

    condition = ContextVarCondition(
        context_var=context_variable,
        return_value_test=ReturnValueTest("==", 19),
    )

    assert condition.context_var == context_variable
    assert condition.return_value_test.comparator == "=="
    assert condition.return_value_test.value == 19
    assert condition.return_value_test.eval(19)


def test_context_var_condition_repr(rpc_condition):
    condition = ContextVarCondition(
        context_var=":contextVar",
        return_value_test=ReturnValueTest("==", 19),
    )
    condition_str = str(condition)
    assert condition.__class__.__name__ in condition_str
    assert "contextVar=:contextVar" in condition_str


def test_context_var_condition_verify(mocker, condition_provider_manager):
    condition = ContextVarCondition(
        context_var=":contextVar",
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


def test_context_var_condition_verify_list(mocker, condition_provider_manager):
    expected = [1, True, "test"]
    condition = ContextVarCondition(
        context_var=":contextVar",
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


def test_context_var_condition_schema_validation():
    condition = ContextVarCondition(
        context_var=":contextVar",
        return_value_test=ReturnValueTest("==", 20),
    )
    condition_dict = condition.to_dict()

    # no issues here
    ContextVarCondition.from_dict(condition_dict)

    # no issues with optional name
    condition_dict["name"] = "my_context_var_condition"
    ContextVarCondition.from_dict(condition_dict)

    with pytest.raises(InvalidConditionLingo):
        # no context var defined
        condition_dict = condition.to_dict()
        del condition_dict["contextVar"]
        ContextVarCondition.from_dict(condition_dict)

    with pytest.raises(InvalidConditionLingo):
        # no return value test defined
        condition_dict = condition.to_dict()
        del condition_dict["returnValueTest"]
        ContextVarCondition.from_dict(condition_dict)
