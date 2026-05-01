import json

import pytest

from nucypher.policy.conditions.exceptions import InvalidCondition
from nucypher.policy.conditions.json.json import JsonCondition
from nucypher.policy.conditions.lingo import ConditionLingo, ReturnValueTest


def test_json_condition_initialization():
    condition = JsonCondition(
        data=":myData",
        query="$.store.book[0].price",
        return_value_test=ReturnValueTest("==", 10.5),
    )
    assert condition.data == ":myData"
    assert condition.query == "$.store.book[0].price"


def test_json_condition_invalid_data_not_context_variable():
    """Test that data field must be a context variable."""
    with pytest.raises(InvalidCondition, match="expected a context variable"):
        JsonCondition(
            data="not_a_context_var",
            return_value_test=ReturnValueTest("==", 42),
        )


def test_json_condition_invalid_data_literal_dict():
    """Test that literal dicts are not allowed."""
    with pytest.raises(InvalidCondition, match="expected a context variable"):
        JsonCondition(
            data={"value": 42},
            return_value_test=ReturnValueTest("==", 42),
        )


def test_json_condition_invalid_type():
    with pytest.raises(
        InvalidCondition, match="'condition_type' field - Must be equal to json"
    ):
        _ = JsonCondition(
            condition_type="INVALID_TYPE",
            data=":myData",
            return_value_test=ReturnValueTest("==", 0),
        )


def test_json_condition_verify_with_dict():
    """Test verifying a dict from context."""
    data = {"store": {"book": [{"price": 10.5}]}}
    condition = JsonCondition(
        data=":apiResult",
        query="$.store.book[0].price",
        return_value_test=ReturnValueTest("==", 10.5),
    )
    result, value = condition.verify(**{":apiResult": data})
    assert result is True
    assert value == 10.5


def test_json_condition_verify_with_string():
    """Test verifying a string value from nested query."""
    data = {"store": {"book": [{"title": "Test Title"}]}}
    condition = JsonCondition(
        data=":apiResult",
        query="$.store.book[0].title",
        return_value_test=ReturnValueTest("==", "'Test Title'"),
    )
    result, value = condition.verify(**{":apiResult": data})
    assert result is True
    assert value == "Test Title"


def test_json_condition_verify_primitive_no_query():
    """Test verifying a primitive value directly (no query)."""
    condition = JsonCondition(
        data=":count",
        return_value_test=ReturnValueTest(">", 50),
    )
    result, value = condition.verify(**{":count": 100})
    assert result is True
    assert value == 100


def test_json_condition_with_context_variable_in_query():
    """Test using context variables in both data and query."""
    data = {"prices": {"usd": 100, "eur": 90}}
    condition = JsonCondition(
        data=":priceData",
        query="$.prices.:currency",
        return_value_test=ReturnValueTest("==", 100),
    )
    context = {":priceData": data, ":currency": "usd"}
    result, value = condition.verify(**context)
    assert result is True
    assert value == 100


def test_json_condition_from_lingo_expression():
    lingo_dict = {
        "conditionType": "json",
        "data": ":apiResult",
        "query": "$.store.book[0].price",
        "returnValueTest": {
            "comparator": "==",
            "value": 10.5,
        },
    }

    cls = ConditionLingo.resolve_condition_class(lingo_dict, version=1)
    assert cls == JsonCondition

    lingo_json = json.dumps(lingo_dict)
    condition = JsonCondition.from_json(lingo_json)
    assert isinstance(condition, JsonCondition)
    assert condition.to_dict() == lingo_dict


def test_json_condition_json_path_multiple_results():
    data = {"store": {"book": [{"price": 1}, {"price": 2}]}}
    condition = JsonCondition(
        data=":data",
        query="$.store.book[*].price",
        return_value_test=ReturnValueTest("==", [1, 2]),
    )
    assert condition.verify(**{":data": data})


def test_json_condition_invalid_jsonpath_syntax():
    """Test that invalid JSONPath syntax is caught during initialization."""
    with pytest.raises(InvalidCondition, match="not a valid JSONPath expression"):
        JsonCondition(
            data=":data",
            query="$[invalid syntax",  # Invalid JSONPath
            return_value_test=ReturnValueTest("==", 10.5),
        )


def test_json_condition_no_matches_found():
    """Test that a query with no matches raises ConditionEvaluationFailed."""
    from nucypher.policy.conditions.exceptions import ConditionEvaluationFailed

    data = {"store": {"book": [{"price": 10.5}]}}
    condition = JsonCondition(
        data=":data",
        query="$.store.nonexistent",  # Path doesn't exist
        return_value_test=ReturnValueTest("==", 10.5),
    )
    with pytest.raises(ConditionEvaluationFailed, match="No matches found"):
        condition.verify(**{":data": data})


def test_json_condition_jsonpath_error_with_context_variable():
    """Test JSONPath errors during verify when using context variables."""
    from nucypher.policy.conditions.exceptions import ConditionEvaluationFailed

    # Create a condition with a context variable in the query
    # The actual query will be resolved at verify time, so we can test runtime errors
    data = {"store": {"book": [{"price": 10.5}]}}
    condition = JsonCondition(
        data=":data",
        query="$.store.:field",
        return_value_test=ReturnValueTest("==", 10.5),
    )

    # Verify with a context variable that creates an invalid path
    with pytest.raises(ConditionEvaluationFailed, match="No matches found"):
        condition.verify(**{":data": data, ":field": "nonexistent"})


def test_json_condition_jsonpath_parser_error_at_runtime():
    """Test that JSONPath parser errors at runtime are caught."""
    from nucypher.policy.conditions.exceptions import ConditionEvaluationFailed

    # Use context variable to inject invalid syntax at runtime (bypassing validation)
    data = {"store": {"book": [{"price": 10.5}]}}
    condition = JsonCondition(
        data=":data",
        query="$.:invalid_syntax",  # Context variable will inject invalid syntax
        return_value_test=ReturnValueTest("==", 10.5),
    )

    # The context variable resolves to invalid JSONPath syntax at runtime
    with pytest.raises(ConditionEvaluationFailed, match="JSONPath error"):
        condition.verify(**{":data": data, ":invalid_syntax": "[invalid syntax"})


def test_json_condition_verify_with_list():
    """Test verifying a list from context."""
    data = [{"id": 1}, {"id": 2}, {"id": 3}]
    condition = JsonCondition(
        data=":listData",
        query="$[0].id",
        return_value_test=ReturnValueTest("==", 1),
    )
    result, value = condition.verify(**{":listData": data})
    assert result is True
    assert value == 1


def test_json_condition_context_variable_with_json_string():
    """Test that JSON strings from context variables are automatically parsed."""
    json_string = '{"store": {"book": [{"price": 10.5}]}}'
    condition = JsonCondition(
        data=":jsonData",
        query="$.store.book[0].price",
        return_value_test=ReturnValueTest("==", 10.5),
    )
    result, value = condition.verify(**{":jsonData": json_string})
    assert result is True
    assert value == 10.5


def test_json_condition_context_variable_with_json_array_string():
    """Test that JSON array strings from context variables are parsed."""
    json_string = '[{"id": 1}, {"id": 2}]'
    condition = JsonCondition(
        data=":arrayData",
        query="$[0].id",
        return_value_test=ReturnValueTest("==", 1),
    )
    result, value = condition.verify(**{":arrayData": json_string})
    assert result is True
    assert value == 1


def test_json_condition_context_variable_with_invalid_json_string():
    """Test that invalid JSON strings raise an error."""
    invalid_json = '{"invalid": json}'
    condition = JsonCondition(
        data=":badJson",
        query="$.value",
        return_value_test=ReturnValueTest("==", 42),
    )
    with pytest.raises(InvalidCondition, match="contains invalid JSON string"):
        condition.verify(**{":badJson": invalid_json})
