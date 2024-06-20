from typing import Any, Optional, Tuple

import requests
from jsonpath_ng.exceptions import JsonPathLexerError, JsonPathParserError
from jsonpath_ng.ext import parse
from marshmallow import ValidationError, fields, post_load, validate
from marshmallow.fields import Field

from nucypher.policy.conditions.base import AccessControlCondition
from nucypher.policy.conditions.exceptions import (
    ConditionEvaluationFailed,
    InvalidCondition,
)
from nucypher.policy.conditions.lingo import ConditionType, ReturnValueTest
from nucypher.policy.conditions.utils import CamelCaseSchema
from nucypher.utilities.logging import Logger


class JSONPathField(Field):
    default_error_messages = {"invalid": "Not a valid JSONPath expression."}

    def _deserialize(self, value, attr, data, **kwargs):
        if not isinstance(value, str):
            self.fail("invalid")
        try:
            parse(value)
        except (JsonPathLexerError, JsonPathParserError):
            self.fail("invalid")
        return value


class OffchainCondition(AccessControlCondition):
    """
    An offchain condition is a condition that can be evaluated by reading from a JSON
    endpoint. This may be a REST service but the only requirement is that
    the response is JSON and can be parsed using jsonpath.
    """

    CONDITION_TYPE = ConditionType.OFFCHAIN.value
    LOGGER = Logger("nucypher.policy.conditions.offchain")

    class Schema(CamelCaseSchema):

        name = fields.Str(required=False)
        condition_type = fields.Str(
            validate=validate.Equal(ConditionType), required=True
        )
        endpoint = fields.Str(required=True)
        query = JSONPathField(required=True)

        def validate_query(self, value):
            try:
                parse(value)
            except Exception as e:
                raise ValidationError(f"Invalid JSONPath query: {e}")

        @post_load
        def make(self, data, **kwargs):
            return OffchainCondition(**data)

    def __init__(
        self,
        endpoint: str,
        query: Optional[str],
        return_value_test: ReturnValueTest,
        headers: Optional[dict] = None,
        parameters: Optional[dict] = None,
        condition_type: str = ConditionType.OFFCHAIN.value,
    ):
        if condition_type != self.CONDITION_TYPE:
            raise InvalidCondition(
                f"{self.__class__.__name__} must be instantiated with the {self.CONDITION_TYPE} type."
            )

        self.endpoint = endpoint
        self.headers = headers
        self.parameters = parameters
        self.query = query
        self.return_value_test = return_value_test
        self.logger = self.LOGGER

    def fetch(self) -> requests.Response:
        """Fetches data from the endpoint."""
        try:
            response = requests.get(
                self.endpoint, params=self.parameters, headers=self.headers
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

        return response

    def deserialize_response(self, response: requests.Response) -> Any:
        """Deserializes the JSON response from the endpoint."""
        try:
            data = response.json()
        except (requests.exceptions.RequestException, ValueError) as json_error:
            self.logger.error(f"JSON parsing error occurred: {json_error}")
            raise ConditionEvaluationFailed(
                f"Failed to parse JSON response: {json_error}"
            )
        return data

    def query_response(self, data: Any) -> Any:
        try:
            expression = parse(self.query)
            matches = expression.find(data)
            if not matches:
                self.logger.info("No matches found for the JSONPath query.")
                raise ConditionEvaluationFailed(
                    "No matches found for the JSONPath query."
                )
            result = matches[0].value
        except (JsonPathLexerError, JsonPathParserError) as jsonpath_err:
            self.logger.error(f"JSONPath error occurred: {jsonpath_err}")
            raise ConditionEvaluationFailed(f"JSONPath error: {jsonpath_err}")
        return result

    def verify(self, **context) -> Tuple[bool, Any]:
        """
        Verifies the offchain condition is met by performing a read operation on the endpoint
        and evaluating the return value test with the result. Parses the endpoint's JSON response using
        JSONPath.
        """
        response = self.fetch()
        data = self.deserialize_response(response)
        result = self.query_response(data)
        return self.return_value_test.eval(result), result
