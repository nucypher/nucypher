import pytest
from web3.exceptions import Web3Exception

from nucypher.policy.conditions.base import (
    AccessControlCondition,
)
from nucypher.policy.conditions.exceptions import InvalidCondition
from nucypher.policy.conditions.lingo import (
    ConditionType,
    ConditionVariable,
    OrCompoundCondition,
    SequentialAccessControlCondition,
)


@pytest.fixture(scope="function")
def mock_condition_variables(mocker):
    cond_1 = mocker.Mock(spec=AccessControlCondition)
    cond_1.verify.return_value = (True, 1)
    cond_1.to_dict.return_value = {"value": 1}
    var_1 = ConditionVariable(var_name="var1", condition=cond_1)

    cond_2 = mocker.Mock(spec=AccessControlCondition)
    cond_2.verify.return_value = (True, 2)
    cond_2.to_dict.return_value = {"value": 2}
    var_2 = ConditionVariable(var_name="var2", condition=cond_2)

    cond_3 = mocker.Mock(spec=AccessControlCondition)
    cond_3.verify.return_value = (True, 3)
    cond_3.to_dict.return_value = {"value": 3}
    var_3 = ConditionVariable(var_name="var3", condition=cond_3)

    cond_4 = mocker.Mock(spec=AccessControlCondition)
    cond_4.verify.return_value = (True, 4)
    cond_4.to_dict.return_value = {"value": 4}
    var_4 = ConditionVariable(var_name="var4", condition=cond_4)

    return var_1, var_2, var_3, var_4


@pytest.mark.usefixtures("mock_skip_schema_validation")
def test_invalid_sequential_condition(mock_condition_variables):
    var_1, *others = mock_condition_variables

    # invalid condition type
    with pytest.raises(InvalidCondition, match=ConditionType.SEQUENTIAL.value):
        _ = SequentialAccessControlCondition(
            condition_type=ConditionType.TIME.value,
            condition_variables=list(mock_condition_variables),
        )

    # no variables
    with pytest.raises(InvalidCondition, match="At least two conditions"):
        _ = SequentialAccessControlCondition(
            condition_type=ConditionType.TIME.value,
            condition_variables=[],
        )

    # only one variable
    with pytest.raises(InvalidCondition, match="At least two conditions"):
        _ = SequentialAccessControlCondition(
            condition_type=ConditionType.TIME.value,
            condition_variables=[var_1],
        )

    # too many variables
    too_many_variables = list(mock_condition_variables)
    too_many_variables.extend(mock_condition_variables)  # duplicate list length
    assert len(too_many_variables) > SequentialAccessControlCondition.MAX_NUM_CONDITIONS
    with pytest.raises(InvalidCondition, match="Maximum of"):
        _ = SequentialAccessControlCondition(
            condition_type=ConditionType.TIME.value,
            condition_variables=too_many_variables,
        )


@pytest.mark.usefixtures("mock_skip_schema_validation")
def test_nested_sequential_condition_too_many_nested_levels(mock_condition_variables):
    var_1, var_2, var_3, var_4 = mock_condition_variables

    with pytest.raises(
        InvalidCondition, match="nested levels of multi-conditions are allowed"
    ):
        _ = (
            SequentialAccessControlCondition(
                condition_variables=[
                    var_1,
                    ConditionVariable(
                        "seq_1",
                        SequentialAccessControlCondition(
                            condition_variables=[
                                var_2,
                                ConditionVariable(
                                    "seq_2",
                                    SequentialAccessControlCondition(
                                        condition_variables=[
                                            var_3,
                                            var_4,
                                        ],
                                    ),
                                ),
                            ],
                        ),
                    ),
                ]
            ),
        )


@pytest.mark.usefixtures("mock_skip_schema_validation")
def test_nested_compound_condition_too_many_nested_levels(mock_condition_variables):
    var_1, var_2, var_3, var_4 = mock_condition_variables

    with pytest.raises(
        InvalidCondition, match="nested levels of multi-conditions are allowed"
    ):
        _ = SequentialAccessControlCondition(
            condition_variables=[
                ConditionVariable(
                    "var1",
                    OrCompoundCondition(
                        operands=[
                            var_1.condition,
                            SequentialAccessControlCondition(
                                condition_variables=[
                                    var_2,
                                    var_3,
                                ]
                            ),
                        ]
                    ),
                ),
                var_4,
            ],
        )


@pytest.mark.usefixtures("mock_skip_schema_validation")
def test_sequential_condition(mock_condition_variables):
    var_1, var_2, var_3, var_4 = mock_condition_variables

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


@pytest.mark.usefixtures("mock_skip_schema_validation")
def test_sequential_condition_all_prior_vars_passed_to_subsequent_calls(
    mock_condition_variables,
):
    var_1, var_2, var_3, var_4 = mock_condition_variables

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


@pytest.mark.usefixtures("mock_skip_schema_validation")
def test_sequential_condition_a_call_fails(mock_condition_variables):
    var_1, var_2, var_3, var_4 = mock_condition_variables

    var_4.condition.verify.side_effect = Web3Exception

    sequential_condition = SequentialAccessControlCondition(
        condition_variables=[var_1, var_2, var_3, var_4],
    )

    with pytest.raises(Web3Exception):
        _ = sequential_condition.verify(providers={})
