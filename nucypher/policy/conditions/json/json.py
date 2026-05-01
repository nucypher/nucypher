import json
from typing import Any, Optional, Tuple

from marshmallow import ValidationError, fields, post_load, validate, validates

from nucypher.policy.conditions.base import Condition
from nucypher.policy.conditions.context import (
    is_context_variable,
    resolve_any_context_variables,
)
from nucypher.policy.conditions.exceptions import InvalidCondition
from nucypher.policy.conditions.json.base import JSONPathField
from nucypher.policy.conditions.json.utils import query_json_data
from nucypher.policy.conditions.lingo import ConditionType, ReturnValueTest


class JsonCondition(Condition):
    """
    A JSON condition evaluates JSON-compatible data from a context variable.

    The data must be provided as a context variable (e.g., ':previousResult')
    which typically comes from a previous condition in a Sequential workflow.
    An optional JSONPath query can be applied to extract a specific value.
    """

    CONDITION_TYPE = ConditionType.JSON.value

    class Schema(Condition.Schema):
        condition_type = fields.Str(
            validate=validate.Equal(ConditionType.JSON.value), required=True
        )
        data = fields.Str(required=True)
        query = JSONPathField(required=False, allow_none=True)
        return_value_test = fields.Nested(ReturnValueTest.Schema(), required=True)

        @validates("data")
        def validate_data(self, value):
            if not is_context_variable(value):
                raise ValidationError(
                    f"Invalid value for data; expected a context variable, but got '{value}'"
                )

        @post_load
        def make(self, data, **kwargs):
            return JsonCondition(**data)

    def __init__(
        self,
        data: str,
        return_value_test: ReturnValueTest,
        query: Optional[str] = None,
        condition_type: Optional[str] = ConditionType.JSON.value,
        name: Optional[str] = None,
    ):
        self.data = data
        self.query = query
        self.return_value_test = return_value_test

        super().__init__(condition_type=condition_type, name=name)

    def verify(self, **context) -> Tuple[bool, Any]:
        """
        Verifies the JSON condition by executing the query and evaluating the result.
        """
        # Resolve context variables in data if needed
        resolved_data = resolve_any_context_variables(self.data, **context)

        # If resolved data is a JSON string, parse it
        if isinstance(resolved_data, str):
            try:
                resolved_data = json.loads(resolved_data)
            except (json.JSONDecodeError, ValueError) as e:
                raise InvalidCondition(
                    f"Context variable '{self.data}' contains invalid JSON string: {e}"
                ) from e

        # Apply JSONPath query
        result = query_json_data(resolved_data, self.query, **context)

        # Evaluate against return value test
        resolved_return_value_test = self.return_value_test.with_resolved_context(
            **context
        )
        eval_result = resolved_return_value_test.eval(result)

        return eval_result, result
