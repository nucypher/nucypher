from typing import Any, Optional, Tuple

import requests
from jsonpath_ng.exceptions import JsonPathLexerError, JsonPathParserError
from jsonpath_ng.ext import parse
from marshmallow import ValidationError, fields, post_load, validate, validates
from marshmallow.fields import Field, Url

from nucypher.policy.conditions.base import ExecutionCall
from nucypher.policy.conditions.context import (
    is_context_variable,
    resolve_context_variable,
)
from nucypher.policy.conditions.exceptions import (
    ConditionEvaluationFailed,
    InvalidCondition,
)
from nucypher.policy.conditions.lingo import (
    ConditionType,
    ExecutionCallAccessControlCondition,
    ReturnValueTest,
)
from nucypher.utilities.logging import Logger


class JSONPathField(Field):
    default_error_messages = {
        "invalidType": "Expression of type {value} is not valid for JSONPath",
        "invalid": "'{value}' is not a valid JSONPath expression",
    }

    def _deserialize(self, value, attr, data, **kwargs):
        if not isinstance(value, str):
            raise self.make_error("invalidType", value=type(value))
        try:
            parse(value)
        except (JsonPathLexerError, JsonPathParserError):
            raise self.make_error("invalid", value=value)
        return value


class JsonApiCall(ExecutionCall):
    TIMEOUT = 5  # seconds

    class Schema(ExecutionCall.Schema):
        endpoint = Url(required=True, relative=False, schemes=["https"])
        parameters = fields.Dict(required=False, allow_none=True)
        query = JSONPathField(required=False, allow_none=True)
        authorization_token = fields.Str(required=False, allow_none=True)

        @post_load
        def make(self, data, **kwargs):
            return JsonApiCall(**data)

        @validates("authorization_token")
        def validate_auth_token(self, value):
            if value and not is_context_variable(value):
                raise ValidationError(
                    f"Invalid value for authorization token; expected a context variable, but got '{value}'"
                )

    def __init__(
        self,
        endpoint: str,
        parameters: Optional[dict] = None,
        query: Optional[str] = None,
        authorization_token: Optional[str] = None,
    ):
        self.endpoint = endpoint
        self.parameters = parameters or {}
        self.query = query
        self.authorization_token = authorization_token

        self.timeout = self.TIMEOUT
        self.logger = Logger(__name__)

        super().__init__()

    def execute(self, **context) -> Any:
        resolved_authorization_token = None
        if self.authorization_token:
            resolved_authorization_token = resolve_context_variable(
                self.authorization_token, **context
            )

        response = self._fetch(resolved_authorization_token)
        data = self._deserialize_response(response)
        result = self._query_response(data)
        return result

    def _fetch(self, authorization_token: str = None) -> requests.Response:
        """Fetches data from the endpoint."""
        try:
            headers = None
            if authorization_token:
                headers = {"Authorization": f"Bearer {authorization_token}"}

            # TODO what about 'post'? (eg. github graphql - https://docs.github.com/en/graphql/guides/forming-calls-with-graphql#communicating-with-graphql)
            response = requests.get(
                self.endpoint,
                params=self.parameters,
                timeout=self.timeout,
                headers=headers,
            )
            response.raise_for_status()
        except requests.exceptions.HTTPError as http_error:
            self.logger.error(f"HTTP error occurred: {http_error}")
            raise ConditionEvaluationFailed(
                f"Failed to fetch endpoint {self.endpoint}: {http_error}"
            )
        except requests.exceptions.RequestException as request_error:
            self.logger.error(f"Request exception occurred: {request_error}")
            raise InvalidCondition(
                f"Failed to fetch endpoint {self.endpoint}: {request_error}"
            )

        if response.status_code != 200:
            self.logger.error(
                f"Failed to fetch endpoint {self.endpoint}: {response.status_code}"
            )
            raise ConditionEvaluationFailed(
                f"Failed to fetch endpoint {self.endpoint}: {response.status_code}"
            )

        return response

    def _deserialize_response(self, response: requests.Response) -> Any:
        """Deserializes the JSON response from the endpoint."""
        try:
            data = response.json()
        except (requests.exceptions.RequestException, ValueError) as json_error:
            self.logger.error(f"JSON parsing error occurred: {json_error}")
            raise ConditionEvaluationFailed(
                f"Failed to parse JSON response: {json_error}"
            )
        return data

    def _query_response(self, data: Any) -> Any:

        if not self.query:
            return data  # primitive value

        try:
            expression = parse(self.query)
            matches = expression.find(data)
            if not matches:
                message = f"No matches found for the JSONPath query: {self.query}"
                self.logger.info(message)
                raise ConditionEvaluationFailed(message)
        except (JsonPathLexerError, JsonPathParserError) as jsonpath_err:
            self.logger.error(f"JSONPath error occurred: {jsonpath_err}")
            raise ConditionEvaluationFailed(f"JSONPath error: {jsonpath_err}")

        if len(matches) > 1:
            message = (
                f"Ambiguous JSONPath query - Multiple matches found for: {self.query}"
            )
            self.logger.info(message)
            raise ConditionEvaluationFailed(message)
        result = matches[0].value

        return result


class JsonApiCondition(ExecutionCallAccessControlCondition):
    """
    A JSON API condition is a condition that can be evaluated by reading from a JSON
    HTTPS endpoint. The response must return an HTTP 200 with valid JSON in the response body.
    The response will be deserialized as JSON and parsed using jsonpath.
    """

    EXECUTION_CALL_TYPE = JsonApiCall
    CONDITION_TYPE = ConditionType.JSONAPI.value

    class Schema(ExecutionCallAccessControlCondition.Schema, JsonApiCall.Schema):
        condition_type = fields.Str(
            validate=validate.Equal(ConditionType.JSONAPI.value), required=True
        )

        @post_load
        def make(self, data, **kwargs):
            return JsonApiCondition(**data)

    def __init__(
        self,
        endpoint: str,
        return_value_test: ReturnValueTest,
        query: Optional[str] = None,
        parameters: Optional[dict] = None,
        authorization_token: Optional[str] = None,
        condition_type: str = ConditionType.JSONAPI.value,
        name: Optional[str] = None,
    ):
        super().__init__(
            endpoint=endpoint,
            return_value_test=return_value_test,
            query=query,
            parameters=parameters,
            authorization_token=authorization_token,
            condition_type=condition_type,
            name=name,
        )

    @property
    def endpoint(self):
        return self.execution_call.endpoint

    @property
    def query(self):
        return self.execution_call.query

    @property
    def parameters(self):
        return self.execution_call.parameters

    @property
    def timeout(self):
        return self.execution_call.timeout

    @property
    def authorization_token(self):
        return self.execution_call.authorization_token

    @staticmethod
    def _process_result_for_eval(result: Any):
        # strings that are not already quoted will cause a problem for literal_eval
        if not isinstance(result, str):
            return result

        # check if already quoted; if not, quote it
        if not (
            (result.startswith("'") and result.endswith("'"))
            or (result.startswith('"') and result.endswith('"'))
        ):
            quote_type_to_use = '"' if "'" in result else "'"
            result = f"{quote_type_to_use}{result}{quote_type_to_use}"

        return result

    def verify(self, **context) -> Tuple[bool, Any]:
        """
        Verifies the offchain condition is met by performing a read operation on the endpoint
        and evaluating the return value test with the result. Parses the endpoint's JSON response using
        JSONPath.
        """
        result = self.execution_call.execute(**context)
        result_for_eval = self._process_result_for_eval(result)

        resolved_return_value_test = self.return_value_test.with_resolved_context(
            **context
        )
        eval_result = resolved_return_value_test.eval(result_for_eval)  # test
        return eval_result, result
