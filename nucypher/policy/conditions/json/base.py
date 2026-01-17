from abc import ABC
from enum import Enum
from http import HTTPStatus
from typing import Any, Optional, Tuple

import requests
from jsonpath_ng.exceptions import JsonPathLexerError, JsonPathParserError
from jsonpath_ng.ext import parse
from marshmallow.fields import String

from nucypher.policy.conditions.base import ExecutionCall
from nucypher.policy.conditions.context import (
    resolve_any_context_variables,
    string_contains_context_variable,
)
from nucypher.policy.conditions.exceptions import (
    JsonRequestException,
)
from nucypher.policy.conditions.json.auth import AuthorizationType
from nucypher.policy.conditions.json.utils import query_json_data
from nucypher.policy.conditions.lingo import ExecutionCallCondition
from nucypher.utilities.logging import Logger


class HTTPMethod(Enum):
    GET = "GET"
    POST = "POST"


class JsonRequestCall(ExecutionCall, ABC):
    TIMEOUT = 5  # seconds

    def __init__(
        self,
        http_method: HTTPMethod,
        parameters: Optional[dict] = None,
        query: Optional[str] = None,
        authorization_token: Optional[str] = None,
        authorization_type: Optional[AuthorizationType] = None,
    ):

        self.http_method = http_method
        self.parameters = parameters or {}
        self.query = query
        self.authorization_token = authorization_token
        self.authorization_type = authorization_type

        self.timeout = self.TIMEOUT
        self.logger = Logger(__name__)

        super().__init__()

    def _execute(self, endpoint: str, **context) -> Any:
        data = self._fetch(endpoint, **context)
        result = self._query_response(data, **context)
        return result

    def _fetch(self, endpoint: str, **context) -> Any:
        resolved_endpoint = resolve_any_context_variables(endpoint, **context)
        resolved_parameters = resolve_any_context_variables(self.parameters, **context)

        headers = {"Content-Type": "application/json"}
        if self.authorization_token:
            resolved_authorization_token = resolve_any_context_variables(
                self.authorization_token, **context
            )
            # use Bearer token if none is provided
            authorization_type = self.authorization_type or AuthorizationType.BEARER
            headers[authorization_type.header_name()] = authorization_type.header_value(
                resolved_authorization_token
            )

        try:
            if self.http_method == HTTPMethod.GET:
                response = requests.get(
                    resolved_endpoint,
                    params=resolved_parameters,
                    timeout=self.timeout,
                    headers=headers,
                )
            else:
                # POST
                response = requests.post(
                    resolved_endpoint,
                    json=resolved_parameters,
                    timeout=self.timeout,
                    headers=headers,
                )

            response.raise_for_status()
            if response.status_code != HTTPStatus.OK:
                raise JsonRequestException(
                    f"Failed to fetch from endpoint {resolved_endpoint}: {response.status_code}"
                )

        except requests.exceptions.RequestException as request_error:
            raise JsonRequestException(
                f"Failed to fetch from endpoint {resolved_endpoint}: {request_error}"
            )

        try:
            data = response.json()
            return data
        except (requests.exceptions.RequestException, ValueError) as json_error:
            raise JsonRequestException(
                f"Failed to extract JSON response from {resolved_endpoint}: {json_error}"
            )

    def _query_response(self, response_json: Any, **context) -> Any:
        return query_json_data(response_json, self.query, **context)


class JSONPathField(String):
    default_error_messages = {
        "invalidType": "Expression of type {value} is not valid for JSONPath",
        "invalid": "'{value}' is not a valid JSONPath expression",
    }

    def _deserialize(self, value, attr, data, **kwargs):
        if not isinstance(value, str):
            raise self.make_error("invalidType", value=type(value))
        try:
            if not string_contains_context_variable(value):
                parse(value)
        except (JsonPathLexerError, JsonPathParserError) as e:
            raise self.make_error("invalid", value=value) from e
        return value


class BaseJsonRequestCondition(ExecutionCallCondition, ABC):
    def verify(self, **context) -> Tuple[bool, Any]:
        """
        Verifies the JSON condition.

        If return_value_test is None, returns (True, result) - meaning
        successful extraction is considered a passing condition.
        """
        result = self.execution_call.execute(**context)

        if self.return_value_test is None:
            # No test defined - extraction success = condition success
            return True, result

        resolved_return_value_test = self.return_value_test.with_resolved_context(
            **context
        )
        eval_result = resolved_return_value_test.eval(result)  # test
        return eval_result, result
