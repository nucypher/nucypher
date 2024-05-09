import pytest

from nucypher.policy.conditions.base import (
    AccessControlCondition,
    ExecutionCall,
    ExecutionVariable,
)
from nucypher.policy.conditions.exceptions import InvalidCondition
from nucypher.policy.conditions.lingo import (
    ConditionType,
    SequentialAccessControlCondition,
)


@pytest.fixture(scope="function")
def mock_execution_variables(mocker):
    call_1 = mocker.Mock(spec=ExecutionCall)
    call_1.execute.return_value = 1
    var_1 = ExecutionVariable(var_name="var1", call=call_1)

    call_2 = mocker.Mock(spec=ExecutionCall)
    call_2.execute.return_value = 2
    var_2 = ExecutionVariable(var_name="var2", call=call_2)

    call_3 = mocker.Mock(spec=ExecutionCall)
    call_3.execute.return_value = 3
    var_3 = ExecutionVariable(var_name="var3", call=call_3)

    call_4 = mocker.Mock(spec=ExecutionCall)
    call_4.execute.return_value = 4
    var_4 = ExecutionVariable(var_name="var4", call=call_4)

    return var_1, var_2, var_3, var_4


def test_invalid_sequential_condition(mock_execution_variables, rpc_condition):
    # invalid condition type
    with pytest.raises(InvalidCondition, match=ConditionType.SEQUENTIAL.value):
        _ = SequentialAccessControlCondition(
            condition_type=ConditionType.TIME.value,
            variables=list(mock_execution_variables),
            condition=rpc_condition,
        )

    # no variables
    with pytest.raises(InvalidCondition):
        _ = SequentialAccessControlCondition(
            condition_type=ConditionType.TIME.value,
            variables=[],
            condition=rpc_condition,
        )

    # too many variables
    too_many_variables = list(mock_execution_variables)
    too_many_variables.extend(mock_execution_variables)  # duplicate list length
    assert len(too_many_variables) > SequentialAccessControlCondition.MAX_NUM_VARIABLES
    with pytest.raises(InvalidCondition):
        _ = SequentialAccessControlCondition(
            condition_type=ConditionType.TIME.value,
            variables=too_many_variables,
            condition=rpc_condition,
        )


def test_sequential_condition(mocker, mock_execution_variables):
    var_1, var_2, var_3, var_4 = mock_execution_variables

    var_1.call.execute.return_value = 1

    var_2.call.execute = lambda providers, **context: context[f":{var_1.var_name}"] * 2

    var_3.call.execute = lambda providers, **context: context[f":{var_2.var_name}"] * 3

    var_4.call.execute = lambda providers, **context: context[f":{var_3.var_name}"] * 4

    condition = mocker.Mock(spec=AccessControlCondition)
    condition.verify = lambda providers, **context: (
        True,
        context[f":{var_4.var_name}"] * 5,
    )

    sequential_condition = SequentialAccessControlCondition(
        variables=[var_1, var_2, var_3, var_4],
        condition=condition,
    )

    original_context = dict()
    result, value = sequential_condition.verify(providers={}, **original_context)
    assert result is True
    assert value == (1 * 2 * 3 * 4 * 5)
    # only a copy of the context is modified internally
    assert len(original_context) == 0, "original context remains unchanged"
