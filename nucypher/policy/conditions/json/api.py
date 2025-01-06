from typing import Any, Optional

from marshmallow import ValidationError, fields, post_load, validate, validates
from marshmallow.fields import Url
from typing_extensions import override

from nucypher.policy.conditions.context import is_context_variable
from nucypher.policy.conditions.json.base import (
    BaseJsonRequestCondition,
    HTTPMethod,
    JSONPathField,
    JsonRequestCall,
)
from nucypher.policy.conditions.lingo import (
    ConditionType,
    ExecutionCallAccessControlCondition,
    ReturnValueTest,
)
from nucypher.utilities.logging import Logger


class JsonApiCall(JsonRequestCall):
    TIMEOUT = 5  # seconds

    class Schema(JsonRequestCall.Schema):
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
        super().__init__(
            http_method=HTTPMethod.GET,
            parameters=parameters,
            query=query,
            authorization_token=authorization_token,
        )

        self.logger = Logger(__name__)

    @override
    def execute(self, **context) -> Any:
        return super()._execute(endpoint=self.endpoint, **context)


class JsonApiCondition(BaseJsonRequestCondition):
    """
    A JSON API condition is a condition that can be evaluated by performing a GET on a JSON
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
        condition_type: Optional[str] = ConditionType.JSONAPI.value,
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
