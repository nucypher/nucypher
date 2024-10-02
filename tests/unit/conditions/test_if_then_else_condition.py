import pytest
from web3.exceptions import Web3Exception

from nucypher.policy.conditions.base import (
    AccessControlCondition,
)
from nucypher.policy.conditions.exceptions import InvalidCondition
from nucypher.policy.conditions.lingo import (
    ConditionType,
    ConditionVariable,
    IfThenElseCondition,
    OrCompoundCondition,
    SequentialAccessControlCondition,
)


@pytest.fixture(scope="function")
def mock_conditions(mocker):
    cond_1 = mocker.Mock(spec=AccessControlCondition)
    cond_1.verify.return_value = (True, 1)
    cond_1.to_dict.return_value = {"value": 1}

    cond_2 = mocker.Mock(spec=AccessControlCondition)
    cond_2.verify.return_value = (True, 2)
    cond_2.to_dict.return_value = {"value": 2}

    cond_3 = mocker.Mock(spec=AccessControlCondition)
    cond_3.verify.return_value = (True, 3)
    cond_3.to_dict.return_value = {"value": 3}

    return cond_1, cond_2, cond_3


def test_invalid_if_then_else_condition(rpc_condition, time_condition):
    # invalid condition type
    with pytest.raises(InvalidCondition, match=ConditionType.IF_THEN_ELSE.value):
        _ = IfThenElseCondition(
            condition_type=ConditionType.TIME.value,
            if_condition=rpc_condition,
            then_condition=time_condition,
            else_condition=False,
        )


def test_nested_sequential_condition_too_many_nested_levels(
    rpc_condition, time_condition
):
    # causes too many nested multi-conditions when used within a if-then-else condition
    problematic_nested_condition = SequentialAccessControlCondition(
        condition_variables=[
            ConditionVariable("var1", time_condition),
            ConditionVariable(
                "seq_1",
                IfThenElseCondition(
                    if_condition=rpc_condition,
                    then_condition=time_condition,
                    else_condition=rpc_condition,
                ),
            ),
        ]
    )

    # issue with "if"
    with pytest.raises(
        InvalidCondition, match="nested levels of multi-conditions are allowed"
    ):
        _ = IfThenElseCondition(
            if_condition=problematic_nested_condition,
            then_condition=rpc_condition,
            else_condition=True,
        )

    # issue with "then"
    with pytest.raises(
        InvalidCondition, match="nested levels of multi-conditions are allowed"
    ):
        _ = IfThenElseCondition(
            if_condition=rpc_condition,
            then_condition=problematic_nested_condition,
            else_condition=True,
        )

    # issue with "else"
    with pytest.raises(
        InvalidCondition, match="nested levels of multi-conditions are allowed"
    ):
        _ = IfThenElseCondition(
            if_condition=rpc_condition,
            then_condition=time_condition,
            else_condition=problematic_nested_condition,
        )


def test_nested_compound_condition_too_many_nested_levels(
    rpc_condition, time_condition
):
    # causes too many nested multi-conditions when used within a if-then-else condition
    problematic_nested_condition = OrCompoundCondition(
        operands=[
            rpc_condition,
            IfThenElseCondition(
                if_condition=time_condition,
                then_condition=rpc_condition,
                else_condition=time_condition,
            ),
        ]
    )

    # issue with "if"
    with pytest.raises(
        InvalidCondition, match="nested levels of multi-conditions are allowed"
    ):
        _ = IfThenElseCondition(
            if_condition=problematic_nested_condition,
            then_condition=rpc_condition,
            else_condition=True,
        )

    # issue with "then"
    with pytest.raises(
        InvalidCondition, match="nested levels of multi-conditions are allowed"
    ):
        _ = IfThenElseCondition(
            if_condition=rpc_condition,
            then_condition=problematic_nested_condition,
            else_condition=True,
        )

    # issue with "else"
    with pytest.raises(
        InvalidCondition, match="nested levels of multi-conditions are allowed"
    ):
        _ = IfThenElseCondition(
            if_condition=rpc_condition,
            then_condition=time_condition,
            else_condition=problematic_nested_condition,
        )


def test_nested_multi_condition_allowed_levels(rpc_condition, time_condition):
    # does not raise
    _ = IfThenElseCondition(
        if_condition=OrCompoundCondition(
            operands=[
                rpc_condition,
                time_condition,
            ]
        ),
        then_condition=IfThenElseCondition(
            if_condition=rpc_condition,
            then_condition=time_condition,
            else_condition=rpc_condition,
        ),
        else_condition=SequentialAccessControlCondition(
            condition_variables=[
                ConditionVariable("var1", time_condition),
                ConditionVariable("var2", rpc_condition),
            ]
        ),
    )


@pytest.mark.usefixtures("mock_skip_schema_validation")
def test_if_then_else_condition(mock_conditions):
    cond_1, cond_2, cond_3 = mock_conditions

    cond_1.verify.return_value = (True, 1)
    cond_2.verify.return_value = (True, 2)
    cond_3.verify.return_value = (False, 3)

    if_then_else_condition = IfThenElseCondition(
        if_condition=cond_1,
        then_condition=cond_2,
        else_condition=cond_3,
    )

    # then execution happens
    result, value = if_then_else_condition.verify()
    assert result is True
    assert value == [1, 2]

    # else execution happens
    cond_1.verify.return_value = (False, 1)
    result, value = if_then_else_condition.verify()
    assert result is False
    assert value == [1, 3]

    # flip else condition to be sure
    cond_3.verify.return_value = (True, 3)
    result, value = if_then_else_condition.verify()
    assert result is True
    assert value == [1, 3]


@pytest.mark.usefixtures("mock_skip_schema_validation")
def test_if_then_else_condition_else_condition_is_boolean(mock_conditions):
    cond_1, cond_2, _ = mock_conditions

    cond_1.verify.return_value = (False, 1)
    cond_2.verify.return_value = (True, 2)

    if_then_else_condition = IfThenElseCondition(
        if_condition=cond_1,
        then_condition=cond_2,
        else_condition=False,
    )

    # else execution happens - False
    cond_1.verify.return_value = (False, 1)
    result, value = if_then_else_condition.verify()
    assert result is False
    assert value == [1, False]

    if_then_else_condition = IfThenElseCondition(
        if_condition=cond_1,
        then_condition=cond_2,
        else_condition=True,
    )

    # else execution happens - True
    result, value = if_then_else_condition.verify()
    assert result is True
    assert value == [1, True]


@pytest.mark.usefixtures("mock_skip_schema_validation")
def test_if_then_else_condition_call_fails(mock_conditions):
    cond_1, cond_2, cond_3 = mock_conditions
    if_then_else_condition = IfThenElseCondition(
        if_condition=cond_1,
        then_condition=cond_2,
        else_condition=cond_3,
    )

    # if call fails
    cond_1.verify.side_effect = Web3Exception("cond_1 failed")
    with pytest.raises(Web3Exception, match="cond_1 failed"):
        _ = if_then_else_condition.verify()

    # then call fails
    cond_1.verify.side_effect = lambda *args, **kwargs: (True, 1)
    cond_2.verify.side_effect = Web3Exception("cond_2 failed")
    with pytest.raises(Web3Exception, match="cond_2 failed"):
        _ = if_then_else_condition.verify()

    # else call fails
    cond_1.verify.side_effect = lambda *args, **kwargs: (False, 1)
    cond_3.verify.side_effect = Web3Exception("cond_3 failed")
    with pytest.raises(Web3Exception, match="cond_3 failed"):
        _ = if_then_else_condition.verify()
