import pytest
import requests
from marshmallow import ValidationError

from nucypher.policy.conditions.exceptions import (
    ConditionEvaluationFailed,
    InvalidCondition,
)
from nucypher.policy.conditions.lingo import ReturnValueTest
from nucypher.policy.conditions.offchain import JSONPathField, OffchainCondition


def test_basic_offchain_condition_evaluation_with_parameters(
    accounts, condition_providers, mocker
):
    mocked_get = mocker.patch(
        "requests.get",
        return_value=mocker.Mock(
            status_code=200, json=lambda: {"ethereum": {"usd": 0.0}}
        ),
    )

    condition = OffchainCondition(
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


def test_basic_offchain_condition_evaluation_with_headers(
    accounts, condition_providers, mocker
):
    mocked_get = mocker.patch(
        "requests.get",
        return_value=mocker.Mock(
            status_code=200, json=lambda: {"ethereum": {"usd": 0.0}}
        ),
    )

    condition = OffchainCondition(
        endpoint="https://api.coingecko.com/api/v3/simple/price",
        parameters={
            "ids": "ethereum",
            "vs_currencies": "usd",
        },
        headers={"Authorization": "Bearer 1234567890"},
        query="ethereum.usd",
        return_value_test=ReturnValueTest("==", 0.0),
    )

    assert condition.verify() == (True, 0.0)
    assert mocked_get.call_count == 1
    assert mocked_get.call_args[1]["headers"]["Authorization"] == "Bearer 1234567890"


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
    assert "Not a valid JSONPath expression." in str(excinfo.value)


def test_offchain_condition_initialization():
    condition = OffchainCondition(
        endpoint="https://api.example.com/data",
        query="$.store.book[0].price",
        return_value_test=ReturnValueTest("==", 0),
    )
    assert condition.endpoint == "https://api.example.com/data"
    assert condition.query == "$.store.book[0].price"
    assert condition.return_value_test.eval(0)


def test_offchain_condition_invalid_type():
    with pytest.raises(InvalidCondition) as excinfo:
        OffchainCondition(
            endpoint="https://api.example.com/data",
            query="$.store.book[0].price",
            return_value_test=ReturnValueTest("==", 0),
            condition_type="INVALID_TYPE",
        )
    assert "must be instantiated with the offchain type" in str(excinfo.value)


def test_offchain_condition_fetch(mocker):
    mock_response = mocker.Mock(status_code=200)
    mock_response.json.return_value = {"store": {"book": [{"price": "1"}]}}
    mocker.patch("requests.get", return_value=mock_response)

    condition = OffchainCondition(
        endpoint="https://api.example.com/data",
        query="$.store.book[0].price",
        return_value_test=ReturnValueTest("==", "1"),
    )
    response = condition.fetch()
    assert response.status_code == 200
    assert response.json() == {"store": {"book": [{"price": "1"}]}}


def test_offchain_condition_fetch_failure(mocker):
    mocker.patch(
        "requests.get", side_effect=requests.exceptions.RequestException("Error")
    )

    condition = OffchainCondition(
        endpoint="https://api.example.com/data",
        query="$.store.book[0].price",
        return_value_test=ReturnValueTest("==", "1"),
    )
    with pytest.raises(InvalidCondition) as excinfo:
        condition.fetch()
    assert "Failed to fetch endpoint" in str(excinfo.value)


def test_offchain_condition_verify(mocker):
    mock_response = mocker.Mock(status_code=200)
    mock_response.json.return_value = {"store": {"book": [{"price": "1"}]}}
    mocker.patch("requests.get", return_value=mock_response)

    condition = OffchainCondition(
        endpoint="https://api.example.com/data",
        query="$.store.book[0].price",
        return_value_test=ReturnValueTest("==", "1"),
    )
    result, value = condition.verify()
    assert result is True
    assert value == "1"


def test_offchain_condition_verify_invalid_json(mocker):
    mock_response = mocker.Mock(status_code=200)
    mock_response.json.side_effect = requests.exceptions.RequestException("Error")
    mocker.patch("requests.get", return_value=mock_response)

    condition = OffchainCondition(
        endpoint="https://api.example.com/data",
        query="$.store.book[0].price",
        return_value_test=ReturnValueTest("==", "2"),
    )
    with pytest.raises(ConditionEvaluationFailed) as excinfo:
        condition.verify()
    assert "Failed to parse JSON response" in str(excinfo.value)
