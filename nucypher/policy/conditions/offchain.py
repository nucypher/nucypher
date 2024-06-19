from typing import Any, Optional, Tuple

import requests
from jsonpath_ng.exceptions import JsonPathLexerError, JsonPathParserError
from jsonpath_ng.ext import parse
from marshmallow import ValidationError, fields, post_load, validate
from marshmallow.fields import Field

from nucypher.policy.conditions.base import AccessControlCondition
from nucypher.policy.conditions.exceptions import InvalidCondition
from nucypher.policy.conditions.lingo import ConditionType, ReturnValueTest
from nucypher.policy.conditions.utils import CamelCaseSchema


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
        parameters: Optional[dict] = None,
        condition_type: str = ConditionType.OFFCHAIN.value,
    ):

        # internal
        if condition_type != self.CONDITION_TYPE:
            raise InvalidCondition(
                f"{self.__class__.__name__} must be instantiated with the {self.CONDITION_TYPE} type."
            )

        self.endpoint = endpoint
        self.parameters = parameters
        self.query = query
        self.return_value_test = return_value_test

    def fetch(self):
        try:
            response = requests.get(self.endpoint, params=self.parameters)
        except requests.exceptions.RequestException as e:
            raise InvalidCondition(f"Failed to fetch endpoint {self.endpoint}: {e}")
        return response

    def verify(self, **context) -> Tuple[bool, Any]:
        """
        Verifies the offchain condition is met by performing a read operation on the endpoint
        and evaluating the return value test with the result.  Parses the endpoint's JSON response using
        jsonpath.
        """

        response = self.fetch()

        try:
            data = response.json()
        except requests.exceptions.RequestException as e:
            raise InvalidCondition(f"Failed to parse JSON response: {e}")

        expression = parse(self.query)

        # TODO: Uses the first match, is it beneficial to support multiple matches?
        result = expression.find(data)[0].value

        return self.return_value_test.eval(result), result
