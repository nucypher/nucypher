import json
from abc import ABC
from enum import Enum
from http import HTTPStatus
from typing import Any, Optional

import requests
from jsonpath_ng.exceptions import JsonPathLexerError, JsonPathParserError
from jsonpath_ng.ext import parse
from marshmallow.fields import Field

from nucypher.policy.conditions.base import ExecutionCall
from nucypher.policy.conditions.context import (
    resolve_any_context_variables,
    string_contains_context_variable,
)
from nucypher.policy.conditions.exceptions import JsonRequestException
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
    ):

        self.http_method = http_method
        self.parameters = parameters or {}
        self.query = query
        self.authorization_token = authorization_token

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
            headers = {"Authorization": f"Bearer {resolved_authorization_token}"}

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
                    data=json.dumps(resolved_parameters),
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
        if not self.query:
            return response_json  # primitive value

        resolved_query = resolve_any_context_variables(self.query, **context)
        try:
            expression = parse(resolved_query)
            matches = expression.find(response_json)
            if not matches:
                message = f"No matches found for the JSONPath query: {resolved_query}"
                raise JsonRequestException(message)
        except JsonRequestException as jsonpath_err:
            self.logger.error(f"JSONPath error occurred: {jsonpath_err}")
            raise JsonRequestException(
                f"JSONPath error: {jsonpath_err}"
            ) from jsonpath_err

        if len(matches) > 1:
            message = f"Ambiguous JSONPath query - multiple matches found for: {resolved_query}"
            self.logger.info(message)
            raise JsonRequestException(message)
        result = matches[0].value
        return result


class JSONPathField(Field):
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
        except (JsonPathLexerError, JsonPathParserError):
            raise self.make_error("invalid", value=value)
        return value
