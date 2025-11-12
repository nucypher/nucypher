import json

import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec
from web3.exceptions import Web3Exception

from nucypher.policy.conditions.base import (
    Condition,
)
from nucypher.policy.conditions.exceptions import (
    ConditionEvaluationFailed,
    InvalidCondition,
)
from nucypher.policy.conditions.json.json import JsonCondition
from nucypher.policy.conditions.jwt import JWTCondition
from nucypher.policy.conditions.lingo import (
    MAX_VARIABLE_OPERATIONS,
    AtLeastCompoundCondition,
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


def test_sequential_condition_jwt_processing():

    # Setup keys
    private_key_alice = ec.generate_private_key(ec.SECP256R1())
    private_key_bob = ec.generate_private_key(ec.SECP256R1())

    public_key_alice = private_key_alice.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )

    public_key_bob = private_key_bob.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )

    # Signature Policy definition
    jwt_condition_alice = JWTCondition(
        jwt_token=":signed_statement_from_alice",
        algorithm="ES256",
        public_key=public_key_alice,
        return_false_on_failure=True,
    )

    jwt_condition_bob = JWTCondition(
        jwt_token=":signed_statement_from_bob",
        algorithm="ES256",
        public_key=public_key_bob,
        return_false_on_failure=True,
    )

    at_least_one_signed_condition = AtLeastCompoundCondition(
        operands=[jwt_condition_alice, jwt_condition_bob],
        threshold=1,
    )

    at_least_one_expected_statement_condition = AtLeastCompoundCondition(
        operands=[
            JsonCondition(
                data=":statements",
                query="$[0]",
                return_value_test=ReturnValueTest(
                    comparator="==",
                    value=":expected_statement",
                ),
            ),
            JsonCondition(
                data=":statements",
                query="$[1]",
                return_value_test=ReturnValueTest(
                    comparator="==",
                    value=":expected_statement",
                ),
            ),
        ],
        threshold=1,
    )

    accounting_consolidation_condition = SequentialCondition(
        condition_variables=[
            # 1. Validate at least one JWT signature and extract statements
            ConditionVariable(
                var_name="statements",
                condition=at_least_one_signed_condition,
            ),
            # 2. Validate at least one statement matches expected
            ConditionVariable(
                var_name="expected_statement_check",
                condition=at_least_one_expected_statement_condition,
            ),
            # 3. Validate statement content
            ConditionVariable(
                var_name="statement_check_json",
                condition=JsonCondition(
                    data=":expected_statement",
                    query="$.book_status",
                    return_value_test=ReturnValueTest("==", "'consolidated'"),
                ),
            ),
            # 4. More conditions can be used to perform additional checks, for example:
            # - External API calls
            # - On-chain contract calls
        ]
    )

    # Signing statements
    statement = {
        "sales": [
            {"item": "foo", "amount": 1000, "timestamp": 1762456000},
            {"item": "bar", "amount": 1500, "timestamp": 1762455111},
        ],
        "book_status": "consolidated",
    }

    signed_statement_alice = jwt.encode(statement, private_key_alice, algorithm="ES256")
    signed_statement_bob = jwt.encode(statement, private_key_bob, algorithm="ES256")

    # Verification (various success scenarios)
    success_stories = [
        (signed_statement_alice, signed_statement_bob),
        (signed_statement_alice, ""),
        ("", signed_statement_bob),
    ]

    for alice_input, bob_input in success_stories:
        context = {
            ":expected_statement": statement,
            ":signed_statement_from_alice": alice_input,
            ":signed_statement_from_bob": bob_input,
        }
        result, values = accounting_consolidation_condition.verify(
            providers=ConditionProviderManager({}), **context
        )

        assert result is True
        assert len(values) == 3
        # First condition: at least one valid signature
        assert values[0].count(statement) >= 1
        # Second condition: first statement matches expected statement
        assert values[1].count(statement) >= 1
        # Third condition: statement content check
        assert values[2] == "consolidated"

    # Verification (failure scenario)
    context = {
        ":expected_statement": statement,
        ":signed_statement_from_alice": "invalid_jwt_token",
        ":signed_statement_from_bob": "invalid_jwt_token",
    }
    result, values = accounting_consolidation_condition.verify(
        providers=ConditionProviderManager({}), **context
    )

    assert result is False
    assert len(values) == 1
    # First condition failed: all signatures are invalid and returned False
    assert values[0] == ["False", "False"]


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
