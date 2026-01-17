import json

import pytest
from web3.exceptions import Web3Exception

from nucypher.policy.conditions.base import (
    Condition,
)
from nucypher.policy.conditions.exceptions import (
    ConditionEvaluationFailed,
    InvalidCondition,
    InvalidConditionLingo,
)
from nucypher.policy.conditions.json.json import JsonCondition
from nucypher.policy.conditions.lingo import (
    MAX_VARIABLE_OPERATIONS,
    ConditionLingo,
    ConditionType,
    ConditionVariable,
    OrCompoundCondition,
    ReturnValueTest,
    SequentialCondition,
    VariableOperation,
)
from nucypher.policy.conditions.utils import ConditionProviderManager, _eth_to_wei
from nucypher.policy.conditions.var import ContextVariableCondition


@pytest.fixture(scope="function")
def mock_condition_variables(mocker):
    cond_1 = mocker.Mock(spec=Condition)
    cond_1.verify.return_value = (True, 1)
    cond_1.to_dict.return_value = {"value": 1}
    var_1 = ConditionVariable(var_name="var1", condition=cond_1)

    cond_2 = mocker.Mock(spec=Condition)
    cond_2.verify.return_value = (True, 2)
    cond_2.to_dict.return_value = {"value": 2}
    var_2 = ConditionVariable(var_name="var2", condition=cond_2)

    cond_3 = mocker.Mock(spec=Condition)
    cond_3.verify.return_value = (True, 3)
    cond_3.to_dict.return_value = {"value": 3}
    var_3 = ConditionVariable(var_name="var3", condition=cond_3)

    cond_4 = mocker.Mock(spec=Condition)
    cond_4.verify.return_value = (True, 4)
    cond_4.to_dict.return_value = {"value": 4}
    var_4 = ConditionVariable(var_name="var4", condition=cond_4)

    return var_1, var_2, var_3, var_4


def test_invalid_sequential_condition(rpc_condition, time_condition):
    var_1 = ConditionVariable("var1", time_condition)
    var_2 = ConditionVariable("var2", rpc_condition)

    # invalid condition type
    with pytest.raises(InvalidCondition, match=ConditionType.SEQUENTIAL.value):
        _ = SequentialCondition(
            condition_type=ConditionType.TIME.value,
            condition_variables=[var_1, var_2],
        )

    # no variables
    with pytest.raises(InvalidCondition, match="At least two conditions"):
        _ = SequentialCondition(
            condition_variables=[],
        )

    # only one variable
    with pytest.raises(InvalidCondition, match="At least two conditions"):
        _ = SequentialCondition(
            condition_variables=[var_1],
        )

    # too many variables
    too_many_variables = [
        *(var_1,) * SequentialCondition.MAX_NUM_CONDITIONS,
        var_2,
    ]  # one too many
    assert len(too_many_variables) > SequentialCondition.MAX_NUM_CONDITIONS
    with pytest.raises(InvalidCondition, match="Maximum of"):
        _ = SequentialCondition(
            condition_variables=too_many_variables,
        )

    # duplicate var names
    dupe_var = ConditionVariable(var_1.var_name, condition=var_2.condition)
    with pytest.raises(InvalidCondition, match="Duplicate"):
        _ = SequentialCondition(
            condition_variables=[var_1, var_2, dupe_var],
        )

    # duplicate var names in nested sequential condition
    with pytest.raises(InvalidCondition, match="Duplicate"):
        # var_1 is duplicated in the nested condition
        _ = SequentialCondition(
            condition_variables=[
                var_1,
                ConditionVariable(
                    "var3", SequentialCondition(condition_variables=[var_1, var_2])
                ),
            ],
        )


def test_sequential_condition_max_number_of_conditions(rpc_condition):
    sequential_condition = SequentialCondition(
        # uses MAX_NUM_CONDITIONS for SequentialCondition (10), which is more than CompoundCondition.MAX_NUM_CONDITIONS (5)
        condition_variables=[
            ConditionVariable(f"var{i}", rpc_condition)
            for i in range(SequentialCondition.MAX_NUM_CONDITIONS)
        ]
    )
    compound_condition = OrCompoundCondition(
        operands=[
            rpc_condition,
            sequential_condition,
        ]
    )
    lingo = ConditionLingo(condition=compound_condition)
    _ = ConditionLingo.from_dict(lingo.to_dict())


def test_nested_sequential_condition_too_many_nested_levels(
    rpc_condition, time_condition
):
    var_1 = ConditionVariable("var1", time_condition)
    var_2 = ConditionVariable("var2", rpc_condition)
    var_3 = ConditionVariable("var3", time_condition)
    var_4 = ConditionVariable("var4", rpc_condition)

    with pytest.raises(
        InvalidCondition, match="nested levels of multi-conditions are allowed"
    ):
        _ = (
            SequentialCondition(
                condition_variables=[
                    var_1,
                    ConditionVariable(
                        "seq_1",
                        SequentialCondition(
                            condition_variables=[
                                var_2,
                                ConditionVariable(
                                    "seq_2",
                                    SequentialCondition(
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


def test_nested_compound_condition_too_many_nested_levels(
    rpc_condition, time_condition
):
    var_1 = ConditionVariable("var1", time_condition)
    var_2 = ConditionVariable("var2", rpc_condition)
    var_3 = ConditionVariable("var3", time_condition)
    var_4 = ConditionVariable("var4", rpc_condition)

    with pytest.raises(
        InvalidCondition, match="nested levels of multi-conditions are allowed"
    ):
        _ = SequentialCondition(
            condition_variables=[
                ConditionVariable(
                    "var1",
                    OrCompoundCondition(
                        operands=[
                            var_1.condition,
                            SequentialCondition(
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

    sequential_condition = SequentialCondition(
        condition_variables=[var_1, var_2, var_3, var_4],
    )

    original_context = dict()
    result, value = sequential_condition.verify(
        providers=ConditionProviderManager({}), **original_context
    )
    assert result is True
    assert value == [1, 1 * 2, 1 * 2 * 3, 1 * 2 * 3 * 4]
    # only a copy of the context is modified internally
    assert len(original_context) == 0, "original context remains unchanged"


def test_condition_variable_operations_validation(time_condition):
    # empty operations list
    with pytest.raises(ValueError, match="At least one operation"):
        _ = ConditionVariable(
            var_name="var1",
            condition=time_condition,
            operations=[],
        )

    # too many operations
    with pytest.raises(
        ValueError, match=f"Maximum of {MAX_VARIABLE_OPERATIONS} operations allowed"
    ):
        _ = ConditionVariable(
            var_name="var1",
            condition=time_condition,
            operations=[VariableOperation(operation="*=", value=2)]
            * (MAX_VARIABLE_OPERATIONS + 1),
        )


@pytest.mark.usefixtures("mock_skip_schema_validation")
def test_sequential_condition_variable_with_operations(
    mocker, mock_condition_variables
):
    var_1, var_2, var_3, var_4 = mock_condition_variables

    var_1_factor = 10
    my_var_1 = ConditionVariable(
        var_name=var_1.var_name,
        condition=var_1.condition,
        operations=[VariableOperation(operation="*=", value=var_1_factor)],
    )

    var_2_factor = 11
    my_var_2 = ConditionVariable(
        var_name=var_2.var_name,
        condition=var_2.condition,
        operations=[VariableOperation(operation="*=", value=var_2_factor)],
    )

    var_3_factor = 12
    my_var_3 = ConditionVariable(
        var_name=var_3.var_name,
        condition=var_3.condition,
        operations=[VariableOperation(operation="*=", value=var_3_factor)],
    )

    var_4_factor = 13
    my_var_4 = ConditionVariable(
        var_name=var_4.var_name,
        condition=var_4.condition,
        operations=[VariableOperation(operation="*=", value=var_4_factor)],
    )

    def cond_5_verify(providers: ConditionProviderManager, **context):
        # condition variables values modified by operations and stored in context
        assert (
            context[f":{var_1.var_name}"] == var_1.condition.verify()[1] * var_1_factor
        )
        assert (
            context[f":{var_2.var_name}"] == var_2.condition.verify()[1] * var_2_factor
        )
        assert (
            context[f":{var_3.var_name}"] == var_3.condition.verify()[1] * var_3_factor
        )
        assert (
            context[f":{var_4.var_name}"] == var_4.condition.verify()[1] * var_4_factor
        )
        return True, 5

    cond_5 = mocker.Mock(spec=Condition)
    cond_5.verify.side_effect = cond_5_verify
    cond_5.to_dict.return_value = {"value": 5}
    my_var_5 = ConditionVariable(
        var_name="var5",
        condition=cond_5,
    )

    sequential_condition = SequentialCondition(
        condition_variables=[my_var_1, my_var_2, my_var_3, my_var_4, my_var_5],
    )

    original_context = dict()
    result, value = sequential_condition.verify(
        providers=ConditionProviderManager({}), **original_context
    )
    assert result is True
    # value include only original condition values not modified condition variable values
    assert value == [1, 2, 3, 4, 5]
    # only a copy of the context is modified internally
    assert len(original_context) == 0, "original context remains unchanged"


@pytest.mark.usefixtures("mock_skip_schema_validation")
def test_sequential_condition_variable_with_operations_with_context_variables(
    mocker, mock_condition_variables
):
    var_1, var_2, var_3, var_4 = mock_condition_variables

    original_context = {}

    var_1_factor = 10
    original_context[":var_1_factor"] = var_1_factor
    my_var_1 = ConditionVariable(
        var_name=var_1.var_name,
        condition=var_1.condition,
        operations=[VariableOperation(operation="*=", value=":var_1_factor")],
    )

    var_2_factor = 11
    original_context[":var_2_factor"] = var_2_factor
    my_var_2 = ConditionVariable(
        var_name=var_2.var_name,
        condition=var_2.condition,
        operations=[VariableOperation(operation="*=", value=":var_2_factor")],
    )

    var_3_factor = 12
    original_context[":var_3_factor"] = var_3_factor
    my_var_3 = ConditionVariable(
        var_name=var_3.var_name,
        condition=var_3.condition,
        operations=[VariableOperation(operation="*=", value=":var_3_factor")],
    )

    var_4_factor = 13
    original_context[":var_4_factor"] = var_4_factor
    my_var_4 = ConditionVariable(
        var_name=var_4.var_name,
        condition=var_4.condition,
        operations=[VariableOperation(operation="*=", value=":var_4_factor")],
    )

    def cond_5_verify(providers: ConditionProviderManager, **context):
        # condition variables values modified by operations and stored in context
        assert (
            context[f":{var_1.var_name}"] == var_1.condition.verify()[1] * var_1_factor
        )
        assert (
            context[f":{var_2.var_name}"] == var_2.condition.verify()[1] * var_2_factor
        )
        assert (
            context[f":{var_3.var_name}"] == var_3.condition.verify()[1] * var_3_factor
        )
        assert (
            context[f":{var_4.var_name}"] == var_4.condition.verify()[1] * var_4_factor
        )
        return True, 5

    cond_5 = mocker.Mock(spec=Condition)
    cond_5.verify.side_effect = cond_5_verify
    cond_5.to_dict.return_value = {"value": 5}
    my_var_5 = ConditionVariable(
        var_name="var5",
        condition=cond_5,
    )

    sequential_condition = SequentialCondition(
        condition_variables=[my_var_1, my_var_2, my_var_3, my_var_4, my_var_5],
    )

    result, value = sequential_condition.verify(
        providers=ConditionProviderManager({}), **original_context
    )
    assert result is True
    # value include only original condition values not modified condition variable values
    assert value == [1, 2, 3, 4, 5]
    # only a copy of the context is modified internally
    assert len(original_context) == 4, "original context remains unchanged"


@pytest.mark.usefixtures("mock_skip_schema_validation")
def test_sequential_condition_variable_with_failed_operation(mock_condition_variables):
    var_1, var_2, var_3, var_4 = mock_condition_variables

    my_var_1 = ConditionVariable(
        var_name=var_1.var_name,
        condition=var_1.condition,
        operations=[
            VariableOperation(operation="index", value=4)
        ],  # invalid for int result; will fail
    )

    sequential_condition = SequentialCondition(
        condition_variables=[my_var_1, var_2, var_3, var_4],
    )

    original_context = dict()
    with pytest.raises(ConditionEvaluationFailed):
        _ = sequential_condition.verify(
            providers=ConditionProviderManager({}), **original_context
        )
    # only a copy of the context is modified internally
    assert len(original_context) == 0, "original context remains unchanged"


def test_sequential_condition_discord_json_message_processing():
    mock_discord_message_json = {
        "app_permissions": "12345",
        "application_id": "98765",
        "data": {
            "id": "1384813344221040750",
            "name": "tip",
            "options": [
                {"name": "amount", "type": 3, "value": "0.0001"},
                {
                    "name": "recipient",
                    "type": 3,
                    "value": "0xA87722643685B38D37ecc7637ACA9C1E09c8C5e1",
                },
            ],
            "type": 1,
        },
        "token": "abcdefg1234567hijklmnop890",
        "type": 2,
        "version": 1,
    }

    amount_json_condition = JsonCondition(
        data=":discord_message",
        query="$.data.options[?(@.name=='amount')].value",
        return_value_test=ReturnValueTest(
            operations=[
                VariableOperation(operation="float"),
            ],
            comparator=">",
            value=0,
        ),
    )
    recipient_json_condition = JsonCondition(
        data=":discord_message",
        query="$.data.options[?(@.name=='recipient')].value",
        return_value_test=ReturnValueTest(
            comparator="!=",
            value="0x0",
        ),
    )
    sequential_condition = SequentialCondition(
        condition_variables=[
            ConditionVariable(
                var_name="amount1",
                condition=amount_json_condition,
                operations=[
                    # ethToWei can convert value from string
                    VariableOperation(operation="ethToWei"),
                ],
            ),
            # amount2 is redundant, but we check that casting to float works on string value
            ConditionVariable(
                var_name="amount2",
                condition=amount_json_condition,
                operations=[
                    VariableOperation(operation="float"),
                    VariableOperation(operation="ethToWei"),
                ],
            ),
            ConditionVariable(
                var_name="recipient",
                condition=recipient_json_condition,
            ),
            ConditionVariable(
                var_name="amount1Check",
                condition=ContextVariableCondition(
                    context_variable=":amount1",
                    return_value_test=ReturnValueTest(
                        comparator="==", value=_eth_to_wei(0.0001)
                    ),
                ),
            ),
            ConditionVariable(
                var_name="amount2Check",
                condition=ContextVariableCondition(
                    context_variable=":amount2",
                    return_value_test=ReturnValueTest(
                        comparator="==", value=":amount1"
                    ),
                ),
            ),
            ConditionVariable(
                var_name="recipientCheck",
                condition=ContextVariableCondition(
                    context_variable=":recipient",
                    return_value_test=ReturnValueTest(
                        comparator="==",
                        value="0xA87722643685B38D37ecc7637ACA9C1E09c8C5e1",
                    ),
                ),
            ),
        ]
    )

    context = {":discord_message": json.dumps(mock_discord_message_json)}
    result, value = sequential_condition.verify(
        providers=ConditionProviderManager({}), **context
    )
    assert result is True


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

    sequential_condition = SequentialCondition(
        condition_variables=[var_1, var_2, var_3, var_4],
    )

    expected_var_1_value = 1
    expected_var_2_value = expected_var_1_value + 1
    expected_var_3_value = expected_var_1_value + expected_var_2_value + 1

    original_context = dict()
    result, value = sequential_condition.verify(
        providers=ConditionProviderManager({}), **original_context
    )
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

    sequential_condition = SequentialCondition(
        condition_variables=[var_1, var_2, var_3, var_4],
    )

    with pytest.raises(Web3Exception):
        _ = sequential_condition.verify(providers=ConditionProviderManager({}))


# Tests for optional returnValueTest feature.
#
# When a condition is inside a ConditionVariable (sequential conditions),
# returnValueTest can be omitted. In this case:
# - The condition returns (True, extracted_value) if extraction succeeds
# - Operations on ConditionVariable still work


def test_json_condition_without_return_value_test_in_condition_variable():
    """JsonCondition without returnValueTest inside ConditionVariable is valid."""
    mock_discord_message_json = {
        "data": {
            "options": [
                {"name": "amount", "value": "0.0001"},
                {"name": "recipient", "value": "0xABC123"},
            ],
        },
    }

    # JsonCondition without returnValueTest - pure extraction
    amount_json_condition = JsonCondition(
        data=":discord_message",
        query="$.data.options[?(@.name=='amount')].value",
        # No returnValueTest - this is the key test
    )

    # Second condition with returnValueTest - validates the extracted value
    validate_condition = ContextVariableCondition(
        context_variable=":amount",
        return_value_test=ReturnValueTest(
            comparator="==",
            value="0.0001",
        ),
    )

    sequential_condition = SequentialCondition(
        condition_variables=[
            ConditionVariable(
                var_name="amount",
                condition=amount_json_condition,
            ),
            ConditionVariable(
                var_name="validated",
                condition=validate_condition,
            ),
        ]
    )

    context = {":discord_message": json.dumps(mock_discord_message_json)}
    result, values = sequential_condition.verify(
        providers=ConditionProviderManager({}), **context
    )

    assert result is True
    assert values[0] == "0.0001"  # Extracted value from JSON
    assert values[1] == "0.0001"  # Validated value


def test_json_condition_without_return_value_test_with_operations():
    """JsonCondition without returnValueTest but with ConditionVariable operations."""
    mock_discord_message_json = {
        "data": {
            "options": [{"name": "amount", "value": "0.0001"}],
        },
    }

    # JsonCondition without returnValueTest - pure extraction
    amount_json_condition = JsonCondition(
        data=":discord_message",
        query="$.data.options[?(@.name=='amount')].value",
        # No returnValueTest
    )

    # Validate the transformed value
    validate_condition = ContextVariableCondition(
        context_variable=":amount",
        return_value_test=ReturnValueTest(
            comparator="==",
            value=_eth_to_wei(0.0001),
        ),
    )

    sequential_condition = SequentialCondition(
        condition_variables=[
            ConditionVariable(
                var_name="amount",
                condition=amount_json_condition,
                operations=[
                    VariableOperation(operation="ethToWei"),
                ],
            ),
            ConditionVariable(
                var_name="validated",
                condition=validate_condition,
            ),
        ]
    )

    context = {":discord_message": json.dumps(mock_discord_message_json)}
    result, values = sequential_condition.verify(
        providers=ConditionProviderManager({}), **context
    )

    assert result is True
    # values[0] is the raw extracted value before operations
    assert values[0] == "0.0001"
    # values[1] is the transformed value from the second condition
    assert values[1] == _eth_to_wei(0.0001)


def test_context_variable_condition_without_return_value_test():
    """ContextVariableCondition without returnValueTest inside ConditionVariable."""
    # First condition extracts with returnValueTest
    first_condition = JsonCondition(
        data=":input",
        query="$.value",
        return_value_test=ReturnValueTest(comparator=">", value=0),
    )

    # Second condition: pure passthrough without returnValueTest
    passthrough_condition = ContextVariableCondition(
        context_variable=":extracted",
        # No returnValueTest - just pass the value through
    )

    # Third condition validates
    validate_condition = ContextVariableCondition(
        context_variable=":passthrough",
        return_value_test=ReturnValueTest(comparator="==", value=42),
    )

    sequential_condition = SequentialCondition(
        condition_variables=[
            ConditionVariable(var_name="extracted", condition=first_condition),
            ConditionVariable(var_name="passthrough", condition=passthrough_condition),
            ConditionVariable(var_name="validated", condition=validate_condition),
        ]
    )

    context = {":input": json.dumps({"value": 42})}
    result, values = sequential_condition.verify(
        providers=ConditionProviderManager({}), **context
    )

    assert result is True
    assert values[0] == 42
    assert values[1] == 42  # Passthrough value
    assert values[2] == 42  # Validated value


def test_standalone_json_condition_requires_return_value_test():
    """JsonCondition outside ConditionVariable requires returnValueTest."""
    # This should fail because returnValueTest is required outside ConditionVariable
    condition_dict = {
        "version": "1.0.0",
        "condition": {
            "conditionType": "json",
            "data": ":someData",
            "query": "$.value",
            # No returnValueTest - should fail
        },
    }

    with pytest.raises(InvalidConditionLingo, match="returnValueTest"):
        ConditionLingo.from_dict(condition_dict)


def test_standalone_context_variable_condition_requires_return_value_test():
    """ContextVariableCondition outside ConditionVariable requires returnValueTest."""
    condition_dict = {
        "version": "1.0.0",
        "condition": {
            "conditionType": "context-variable",
            "contextVariable": ":someVar",
            # No returnValueTest - should fail
        },
    }

    with pytest.raises(InvalidConditionLingo, match="returnValueTest"):
        ConditionLingo.from_dict(condition_dict)


def test_sequential_with_mixed_conditions():
    """Sequential condition with some conditions having returnValueTest and some without."""
    mock_data = {
        "amount": "100",
        "recipient": "0xABC",
    }

    # First condition: extraction without returnValueTest
    extract_amount = JsonCondition(
        data=":data",
        query="$.amount",
        # No returnValueTest
    )

    # Second condition: extraction with returnValueTest (validation)
    extract_and_validate_recipient = JsonCondition(
        data=":data",
        query="$.recipient",
        return_value_test=ReturnValueTest(
            comparator="!=",
            value="0x0",
        ),
    )

    # Third condition: validate amount
    validate_amount = ContextVariableCondition(
        context_variable=":extractedAmount",
        return_value_test=ReturnValueTest(
            comparator="==",
            value="100",
        ),
    )

    sequential_condition = SequentialCondition(
        condition_variables=[
            ConditionVariable(var_name="extractedAmount", condition=extract_amount),
            ConditionVariable(
                var_name="validatedRecipient",
                condition=extract_and_validate_recipient,
            ),
            ConditionVariable(var_name="finalCheck", condition=validate_amount),
        ]
    )

    context = {":data": json.dumps(mock_data)}
    result, values = sequential_condition.verify(
        providers=ConditionProviderManager({}), **context
    )

    assert result is True
    assert values[0] == "100"  # Extracted amount (no returnValueTest)
    assert values[1] == "0xABC"  # Validated recipient (with returnValueTest)
    assert values[2] == "100"  # Final validated amount


def test_serialization_roundtrip_without_return_value_test():
    """Condition without returnValueTest serializes and deserializes correctly."""
    # Create a sequential condition with a nested condition without returnValueTest
    condition_dict = {
        "version": "1.0.0",
        "condition": {
            "conditionType": "sequential",
            "conditionVariables": [
                {
                    "varName": "extracted",
                    "condition": {
                        "conditionType": "json",
                        "data": ":input",
                        "query": "$.value",
                        # No returnValueTest
                    },
                },
                {
                    "varName": "validated",
                    "condition": {
                        "conditionType": "context-variable",
                        "contextVariable": ":extracted",
                        "returnValueTest": {
                            "comparator": "==",
                            "value": 42,
                        },
                    },
                },
            ],
        },
    }

    # Deserialize
    lingo = ConditionLingo.from_dict(condition_dict)

    # Serialize back
    serialized = lingo.to_dict()

    # Check that the first condition has no returnValueTest
    first_condition = serialized["condition"]["conditionVariables"][0]["condition"]
    assert "returnValueTest" not in first_condition

    # Check that the second condition still has returnValueTest
    second_condition = serialized["condition"]["conditionVariables"][1]["condition"]
    assert "returnValueTest" in second_condition
    assert second_condition["returnValueTest"]["comparator"] == "=="
    assert second_condition["returnValueTest"]["value"] == 42


def test_verify_returns_true_without_return_value_test():
    """Verify returns (True, value) when returnValueTest is None."""
    # Create JsonCondition without returnValueTest
    json_cond = JsonCondition(
        data=":input",
        query="$.value",
        # No returnValueTest
    )

    context = {":input": json.dumps({"value": 42})}
    result, value = json_cond.verify(**context)

    # Should return True (extraction succeeded) and the extracted value
    assert result is True
    assert value == 42


def test_context_variable_verify_returns_true_without_return_value_test():
    """ContextVariableCondition.verify returns (True, value) when returnValueTest is None."""
    ctx_cond = ContextVariableCondition(
        context_variable=":myVar",
        # No returnValueTest
    )

    context = {":myVar": "test_value"}
    result, value = ctx_cond.verify(providers=ConditionProviderManager({}), **context)

    assert result is True
    assert value == "test_value"
