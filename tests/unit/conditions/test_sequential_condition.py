import pytest
from web3.exceptions import Web3Exception

from nucypher.policy.conditions.base import (
    AccessControlCondition,
)
from nucypher.policy.conditions.exceptions import InvalidCondition
from nucypher.policy.conditions.lingo import (
    ConditionType,
    ConditionVariable,
    SequentialAccessControlCondition,
)


@pytest.fixture(scope="function")
def mock_execution_variables(mocker):
    cond_1 = mocker.Mock(spec=AccessControlCondition)
    cond_1.verify.return_value = (True, 1)
    var_1 = ConditionVariable(var_name="var1", condition=cond_1)

    cond_2 = mocker.Mock(spec=AccessControlCondition)
    cond_2.verify.return_value = (True, 2)
    var_2 = ConditionVariable(var_name="var2", condition=cond_2)

    cond_3 = mocker.Mock(spec=AccessControlCondition)
    cond_3.verify.return_value = (True, 3)
    var_3 = ConditionVariable(var_name="var3", condition=cond_3)

    cond_4 = mocker.Mock(spec=AccessControlCondition)
    cond_4.verify.return_value = (True, 4)
    var_4 = ConditionVariable(var_name="var4", condition=cond_4)

    return var_1, var_2, var_3, var_4


def test_invalid_sequential_condition(mock_execution_variables, rpc_condition):
    # invalid condition type
    with pytest.raises(InvalidCondition, match=ConditionType.SEQUENTIAL.value):
        _ = SequentialAccessControlCondition(
            condition_type=ConditionType.TIME.value,
            condition_variables=list(mock_execution_variables),
        )

    # no variables
    with pytest.raises(InvalidCondition):
        _ = SequentialAccessControlCondition(
            condition_type=ConditionType.TIME.value,
            condition_variables=[],
        )

    # too many variables
    too_many_variables = list(mock_execution_variables)
    too_many_variables.extend(mock_execution_variables)  # duplicate list length
    assert (
        len(too_many_variables)
        > SequentialAccessControlCondition.MAX_NUM_CONDITION_VARIABLES
    )
    with pytest.raises(InvalidCondition):
        _ = SequentialAccessControlCondition(
            condition_type=ConditionType.TIME.value,
            condition_variables=too_many_variables,
        )


def test_sequential_condition(mocker, mock_execution_variables):
    var_1, var_2, var_3, var_4 = mock_execution_variables

    var_1.condition.verify.return_value = (True, 1)

    var_2.condition.verify = lambda providers, **context: (
        True,
        context[f":{var_1.var_name}"] * 2,
    )

    var_3.condition.verify = lambda providers, **context: (
        True,
        context[f":{var_2.var_name}"] * 3,
    )

    var_4.condition.verify = lambda providers, **context: (
        True,
        context[f":{var_3.var_name}"] * 4,
    )

    sequential_condition = SequentialAccessControlCondition(
        condition_variables=[var_1, var_2, var_3, var_4],
    )

    original_context = dict()
    result, value = sequential_condition.verify(providers={}, **original_context)
    assert result is True
    assert value == [1, 1 * 2, 1 * 2 * 3, 1 * 2 * 3 * 4]
    # only a copy of the context is modified internally
    assert len(original_context) == 0, "original context remains unchanged"


def test_sequential_condition_all_prior_vars_passed_to_subsequent_calls(
    mocker, mock_execution_variables
):
    var_1, var_2, var_3, var_4 = mock_execution_variables

    var_1.condition.verify.return_value = (True, 1)

    var_2.condition.verify = lambda providers, **context: (
        True,
        context[f":{var_1.var_name}"] + 1,
    )

    var_3.condition.verify = lambda providers, **context: (
        True,
        context[f":{var_1.var_name}"] + context[f":{var_2.var_name}"] + 1,
    )

    var_4.condition.verify = lambda providers, **context: (
        True,
        context[f":{var_1.var_name}"]
        + context[f":{var_2.var_name}"]
        + context[f":{var_3.var_name}"]
        + 1,
    )

    sequential_condition = SequentialAccessControlCondition(
        condition_variables=[var_1, var_2, var_3, var_4],
    )

    expected_var_1_value = 1
    expected_var_2_value = expected_var_1_value + 1
    expected_var_3_value = expected_var_1_value + expected_var_2_value + 1

    original_context = dict()
    result, value = sequential_condition.verify(providers={}, **original_context)
    assert result is True
    assert value == [
        expected_var_1_value,
        expected_var_2_value,
        expected_var_3_value,
        (expected_var_1_value + expected_var_2_value + expected_var_3_value + 1),
    ]
    # only a copy of the context is modified internally
    assert len(original_context) == 0, "original context remains unchanged"


def test_sequential_condition_a_call_fails(mocker, mock_execution_variables):
    var_1, var_2, var_3, var_4 = mock_execution_variables

    var_4.condition.verify.side_effect = Web3Exception

    sequential_condition = SequentialAccessControlCondition(
        condition_variables=[var_1, var_2, var_3, var_4],
    )

    with pytest.raises(Web3Exception):
        _ = sequential_condition.verify(providers={})
