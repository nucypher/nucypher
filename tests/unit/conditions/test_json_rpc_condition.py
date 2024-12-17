import json

import pytest
import requests

from nucypher.policy.conditions.exceptions import (
    InvalidCondition,
    JsonRequestException,
)
from nucypher.policy.conditions.json.rpc import JsonRpcCondition
from nucypher.policy.conditions.lingo import (
    ConditionLingo,
    ConditionType,
    ReturnValueTest,
)


def test_json_rpc_condition_initialization():
    condition = JsonRpcCondition(
        endpoint="https://math.example.com/",
        method="subtract",
        query="$.mathresult",
        params=[42, 23],
        return_value_test=ReturnValueTest("==", 19),
    )

    assert condition.endpoint == "https://math.example.com/"
    assert condition.method == "subtract"
    assert condition.query == "$.mathresult"
    assert condition.return_value_test.eval(19)
    assert condition.timeout == JsonRpcCondition.EXECUTION_CALL_TYPE.TIMEOUT


def test_json_rpc_condition_invalid_type():
    with pytest.raises(
        InvalidCondition,
        match=f"'condition_type' field - Must be equal to {ConditionType.JSONRPC.value}",
    ):
        _ = JsonRpcCondition(
            condition_type=ConditionType.JSONAPI.value,
            endpoint="https://math.example.com/",
            method="subtract",
            params=[42, 23],
            return_value_test=ReturnValueTest("==", 19),
        )


def test_https_enforcement():
    with pytest.raises(InvalidCondition, match="Not a valid URL"):
        _ = JsonRpcCondition(
            endpoint="http://math.example.com/",
            method="subtract",
            params=[42, 23],
            return_value_test=ReturnValueTest("==", 19),
        )


def test_invalid_authorization_token():
    with pytest.raises(InvalidCondition, match="Invalid value for authorization token"):
        _ = JsonRpcCondition(
            endpoint="https://math.example.com/",
            method="subtract",
            params=[42, 23],
            return_value_test=ReturnValueTest("==", 19),
            authorization_token="github_pat_123456789",
        )


def test_json_rpc_condition_verify(mocker):
    mock_response = mocker.Mock(status_code=200)
    mock_response.json.return_value = {"jsonrpc": "2.0", "result": 19, "id": 1}
    mocked_method = mocker.patch("requests.post", return_value=mock_response)

    condition = JsonRpcCondition(
        endpoint="https://math.example.com/",
        method="subtract",
        params=[42, 23],
        return_value_test=ReturnValueTest("==", 19),
    )
    success, result = condition.verify()
    assert success is True
    assert result == 19

    assert mocked_method.call_count == 1
    assert mocked_method.call_args.kwargs["json"] == {
        "jsonrpc": "2.0",
        "id": 1,
        "method": condition.method,
        "params": condition.params,
    }


def test_json_rpc_condition_verify_params_as_dict(mocker):
    mock_response = mocker.Mock(status_code=200)
    mock_response.json.return_value = {"jsonrpc": "2.0", "result": 19, "id": 1}
    mocked_method = mocker.patch("requests.post", return_value=mock_response)

    condition = JsonRpcCondition(
        endpoint="https://math.example.com/",
        method="subtract",
        params={
            "value1": 42,
            "value2": 23,
        },
        return_value_test=ReturnValueTest("==", 19),
    )
    success, result = condition.verify()
    assert success is True
    assert result == 19

    assert mocked_method.call_count == 1
    assert mocked_method.call_args.kwargs["json"] == {
        "jsonrpc": "2.0",
        "id": 1,
        "method": condition.method,
        "params": condition.params,
    }


def test_json_rpc_non_200_status(mocker):
    # Mock the requests.get method to return a response with non-JSON content
    mock_response = mocker.Mock()
    mock_response.status_code = 400
    mocker.patch("requests.post", return_value=mock_response)

    condition = JsonRpcCondition(
        endpoint="https://math.example.com/",
        method="subtract",
        params=[42, 23],
        return_value_test=ReturnValueTest("==", 19),
    )

    with pytest.raises(JsonRequestException, match="Failed to fetch from endpoint"):
        condition.verify()


def test_json_rpc_condition_verify_error(mocker):
    mock_response = mocker.Mock(status_code=200)
    error = {
        "jsonrpc": "2.0",
        "error": {"code": -32601, "message": "Method not found"},
        "id": "1",
    }
    mock_response.json.return_value = error
    mocker.patch("requests.post", return_value=mock_response)

    condition = JsonRpcCondition(
        endpoint="https://math.example.com/",
        method="foobar",
        params=[42, 23],
        return_value_test=ReturnValueTest("==", 19),
    )
    with pytest.raises(
        JsonRequestException,
        match=f"code={error['error']['code']}, msg={error['error']['message']}",
    ):
        condition.verify()


def test_json_rpc_condition_verify_invalid_json(mocker):
    mock_response = mocker.Mock(status_code=200)
    mock_response.json.side_effect = requests.exceptions.RequestException("Error")
    mocker.patch("requests.post", return_value=mock_response)

    condition = JsonRpcCondition(
        endpoint="https://math.example.com/",
        method="subtract",
        params=[42, 23],
        return_value_test=ReturnValueTest("==", 19),
    )
    with pytest.raises(JsonRequestException, match="Failed to extract JSON response"):
        condition.verify()


def test_json_rpc_condition_evaluation_with_auth_token(mocker):
    mock_response = mocker.Mock(status_code=200)
    mock_response.json.return_value = {"jsonrpc": "2.0", "result": 19, "id": 1}
    mocked_method = mocker.patch("requests.post", return_value=mock_response)

    condition = JsonRpcCondition(
        endpoint="https://math.example.com/",
        method="subtract",
        params=[42, 23],
        return_value_test=ReturnValueTest("==", 19),
        authorization_token=":authToken",
    )

    assert condition.authorization_token == ":authToken"
    auth_token = "1234567890"
    context = {":authToken": f"{auth_token}"}

    success, result = condition.verify(**context)
    assert success is True
    assert result == 19

    assert mocked_method.call_count == 1
    assert mocked_method.call_args.kwargs["json"] == {
        "jsonrpc": "2.0",
        "id": 1,
        "method": condition.method,
        "params": condition.params,
    }

    assert mocked_method.call_count == 1
    assert (
        mocked_method.call_args.kwargs["headers"]["Authorization"]
        == f"Bearer {auth_token}"
    )


def test_json_rpc_condition_evaluation_with_various_context_variables(mocker):
    mocked_post = mocker.patch(
        "requests.post",
        return_value=mocker.Mock(
            status_code=200, json=lambda: {"result": {"mathresult": 19}}
        ),
    )

    condition = JsonRpcCondition(
        endpoint="https://math.example.com/:version/simple",
        method=":methodContextVar",
        params=[":value1", 23],
        query="$.:queryKey",
        authorization_token=":authToken",
        return_value_test=ReturnValueTest("==", ":expectedResult"),
    )

    auth_token = "1234567890"
    context = {
        ":version": "v3",
        ":methodContextVar": "subtract",  # TODO, should we allow this?
        ":value1": 42,
        ":queryKey": "mathresult",
        ":authToken": f"{auth_token}",
        ":expectedResult": 19,
    }
    assert condition.verify(**context) == (True, 19)
    assert mocked_post.call_count == 1

    call_args = mocked_post.call_args
    assert call_args.args == (f"https://math.example.com/{context[':version']}/simple",)
    assert call_args.kwargs["headers"]["Authorization"] == f"Bearer {auth_token}"
    assert call_args.kwargs["json"] == {
        "jsonrpc": "2.0",
        "id": 1,
        "method": context[":methodContextVar"],
        "params": [42, 23],
    }


def test_json_rpc_condition_from_lingo_expression():
    lingo_dict = {
        "conditionType": ConditionType.JSONRPC.value,
        "endpoint": "https://math.example.com/",
        "method": "subtract",
        "params": [42, 23],
        "query": "$.mathresult",
        "returnValueTest": {
            "comparator": "==",
            "value": 19,
        },
    }

    cls = ConditionLingo.resolve_condition_class(lingo_dict, version=1)
    assert cls == JsonRpcCondition

    lingo_json = json.dumps(lingo_dict)
    condition = JsonRpcCondition.from_json(lingo_json)
    assert isinstance(condition, JsonRpcCondition)
    assert condition.to_dict() == lingo_dict


def test_json_rpc_condition_from_lingo_expression_with_authorization():
    lingo_dict = {
        "conditionType": ConditionType.JSONRPC.value,
        "endpoint": "https://example.com/",
        "method": "subtract",
        "params": {
            "param1": 42,
            "param2": "rando_param",
            "param3": 1.25,
            "param4": True,
        },
        "query": "$.mathresult",
        "authorizationToken": ":authorizationToken",
        "returnValueTest": {
            "comparator": "==",
            "value": 19,
        },
    }

    cls = ConditionLingo.resolve_condition_class(lingo_dict, version=1)
    assert cls == JsonRpcCondition

    lingo_json = json.dumps(lingo_dict)
    condition = JsonRpcCondition.from_json(lingo_json)
    assert isinstance(condition, JsonRpcCondition)
    assert condition.to_dict() == lingo_dict


def test_ambiguous_json_path_multiple_results(mocker):
    mock_response = mocker.Mock(status_code=200)
    mock_response.json.return_value = {
        "result": {"mathresult": [{"answer": 19}, {"answer": -19}]}
    }
    mocker.patch("requests.post", return_value=mock_response)

    condition = JsonRpcCondition(
        endpoint="https://math.example.com/",
        method="subtract",
        params=[42, 23],
        query="$.mathresult[*].answer",
        return_value_test=ReturnValueTest("==", 19),
    )

    with pytest.raises(JsonRequestException, match="Ambiguous JSONPath query"):
        condition.verify()
