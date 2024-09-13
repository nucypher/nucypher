import json

import pytest
import requests
from marshmallow import ValidationError

from nucypher.policy.conditions.exceptions import (
    ConditionEvaluationFailed,
    InvalidCondition,
    InvalidConditionLingo,
)
from nucypher.policy.conditions.lingo import ConditionLingo, ReturnValueTest
from nucypher.policy.conditions.offchain import (
    JsonApiCondition,
    JSONPathField,
)


def test_jsonpath_field_valid():
    field = JSONPathField()
    valid_jsonpath = "$.store.book[0].price"
    result = field.deserialize(valid_jsonpath)
    assert result == valid_jsonpath


def test_jsonpath_field_invalid():
    field = JSONPathField()
    invalid_jsonpath = "invalid jsonpath"
    with pytest.raises(ValidationError) as excinfo:
        field.deserialize(invalid_jsonpath)
    assert f"'{invalid_jsonpath}' is not a valid JSONPath expression" in str(
        excinfo.value
    )


def test_json_api_condition_initialization():
    condition = JsonApiCondition(
        endpoint="https://api.example.com/data",
        query="$.store.book[0].price",
        return_value_test=ReturnValueTest("==", 0),
    )
    assert condition.endpoint == "https://api.example.com/data"
    assert condition.query == "$.store.book[0].price"
    assert condition.return_value_test.eval(0)


def test_json_api_condition_invalid_type():
    with pytest.raises(InvalidCondition) as excinfo:
        JsonApiCondition(
            endpoint="https://api.example.com/data",
            query="$.store.book[0].price",
            return_value_test=ReturnValueTest("==", 0),
            condition_type="INVALID_TYPE",
        )
    assert "must be instantiated with the json-api type" in str(excinfo.value)


def test_https_enforcement():
    with pytest.raises(InvalidConditionLingo) as excinfo:
        JsonApiCondition(
            endpoint="http://api.example.com/data",
            query="$.store.book[0].price",
            return_value_test=ReturnValueTest("==", 0),
        )
    assert "Not a valid URL" in str(excinfo.value)


def test_json_api_condition_with_primitive_response(mocker):
    mock_response = mocker.Mock(status_code=200)
    mock_response.json.return_value = 1
    mocker.patch("requests.get", return_value=mock_response)

    condition = JsonApiCondition(
        endpoint="https://api.example.com/data",
        return_value_test=ReturnValueTest("==", 1),
    )
    success, result = condition.verify()
    assert success is True


def test_json_api_condition_fetch(mocker):
    mock_response = mocker.Mock(status_code=200)
    mock_response.json.return_value = {"store": {"book": [{"title": "Test Title"}]}}
    mocker.patch("requests.get", return_value=mock_response)

    condition = JsonApiCondition(
        endpoint="https://api.example.com/data",
        query="$.store.book[0].title",
        return_value_test=ReturnValueTest("==", "'Test Title'"),
    )
    response = condition.fetch()
    assert response.status_code == 200
    assert response.json() == {"store": {"book": [{"title": "Test Title"}]}}


def test_json_api_condition_fetch_failure(mocker):
    mocker.patch(
        "requests.get", side_effect=requests.exceptions.RequestException("Error")
    )

    condition = JsonApiCondition(
        endpoint="https://api.example.com/data",
        query="$.store.book[0].price",
        return_value_test=ReturnValueTest("==", 1),
    )
    with pytest.raises(InvalidCondition) as excinfo:
        condition.fetch()
    assert "Failed to fetch endpoint" in str(excinfo.value)


def test_json_api_condition_verify(mocker):
    mock_response = mocker.Mock(status_code=200)
    mock_response.json.return_value = {"store": {"book": [{"price": 1}]}}
    mocker.patch("requests.get", return_value=mock_response)

    condition = JsonApiCondition(
        endpoint="https://api.example.com/data",
        query="$.store.book[0].price",
        return_value_test=ReturnValueTest("==", 1),
    )
    result, value = condition.verify()
    assert result is True
    assert value == 1


def test_json_api_condition_verify_string_without_whitespace(mocker):
    mock_response = mocker.Mock(status_code=200)
    mock_response.json.return_value = {"store": {"book": [{"title": "Title"}]}}
    mocker.patch("requests.get", return_value=mock_response)

    condition = JsonApiCondition(
        endpoint="https://api.example.com/data",
        query="$.store.book[0].title",
        return_value_test=ReturnValueTest("==", "'Title'"),
    )
    result, value = condition.verify()
    assert result is True
    assert value == "Title"


def test_json_api_condition_verify_string_with_whitespace(mocker):
    mock_response = mocker.Mock(status_code=200)
    mock_response.json.return_value = {"store": {"book": [{"title": "Test Title"}]}}
    mocker.patch("requests.get", return_value=mock_response)

    condition = JsonApiCondition(
        endpoint="https://api.example.com/data",
        query="$.store.book[0].title",
        return_value_test=ReturnValueTest("==", "'Test Title'"),
    )
    result, value = condition.verify()
    assert result is True
    assert value == "Test Title"


def test_json_api_condition_verify_invalid_json(mocker):
    mock_response = mocker.Mock(status_code=200)
    mock_response.json.side_effect = requests.exceptions.RequestException("Error")
    mocker.patch("requests.get", return_value=mock_response)

    condition = JsonApiCondition(
        endpoint="https://api.example.com/data",
        query="$.store.book[0].price",
        return_value_test=ReturnValueTest("==", 2),
    )
    with pytest.raises(ConditionEvaluationFailed) as excinfo:
        condition.verify()
    assert "Failed to parse JSON response" in str(excinfo.value)


def test_non_json_response(mocker):
    # Mock the requests.get method to return a response with non-JSON content
    mock_response = mocker.Mock()
    mock_response.status_code = 200
    mock_response.json.side_effect = ValueError("No JSON object could be decoded")
    mock_response.text = "This is not JSON"

    mocker.patch("requests.get", return_value=mock_response)

    condition = JsonApiCondition(
        endpoint="https://api.example.com/data",
        query="$.store.book[0].price",
        return_value_test=ReturnValueTest("==", 18),
    )

    with pytest.raises(ConditionEvaluationFailed) as excinfo:
        condition.verify()

    assert "Failed to parse JSON response" in str(excinfo.value)


def test_basic_json_api_condition_evaluation_with_parameters(mocker):
    mocked_get = mocker.patch(
        "requests.get",
        return_value=mocker.Mock(
            status_code=200, json=lambda: {"ethereum": {"usd": 0.0}}
        ),
    )

    condition = JsonApiCondition(
        endpoint="https://api.coingecko.com/api/v3/simple/price",
        parameters={
            "ids": "ethereum",
            "vs_currencies": "usd",
        },
        query="ethereum.usd",
        return_value_test=ReturnValueTest("==", 0.0),
    )

    assert condition.verify() == (True, 0.0)
    assert mocked_get.call_count == 1


def test_json_api_condition_from_lingo_expression():
    lingo_dict = {
        "conditionType": "json-api",
        "endpoint": "https://api.example.com/data",
        "query": "$.store.book[0].price",
        "parameters": {
            "ids": "ethereum",
            "vs_currencies": "usd",
        },
        "returnValueTest": {
            "comparator": "==",
            "value": "0xaDD9D957170dF6F33982001E4c22eCCdd5539118",
        },
    }

    cls = ConditionLingo.resolve_condition_class(lingo_dict, version=1.0)
    assert cls == JsonApiCondition

    lingo_json = json.dumps(lingo_dict)
    condition = JsonApiCondition.from_json(lingo_json)
    assert isinstance(condition, JsonApiCondition)


def test_ambiguous_json_path_multiple_results(mocker):
    mock_response = mocker.Mock(status_code=200)
    mock_response.json.return_value = {"store": {"book": [{"price": 1}, {"price": 2}]}}

    mocker.patch("requests.get", return_value=mock_response)

    condition = JsonApiCondition(
        endpoint="https://api.example.com/data",
        query="$.store.book[*].price",
        return_value_test=ReturnValueTest("==", 1),
    )

    with pytest.raises(ConditionEvaluationFailed) as excinfo:
        condition.verify()

    assert "Ambiguous JSONPath query" in str(excinfo.value)
