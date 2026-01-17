from typing import Any, Optional, Tuple

from marshmallow import (
    ValidationError,
    fields,
    post_load,
    validate,
    validates,
    validates_schema,
)

from nucypher.policy.conditions.base import Condition
from nucypher.policy.conditions.context import (
    is_context_variable,
    resolve_any_context_variables,
)
from nucypher.policy.conditions.lingo import ConditionType, ReturnValueTest
from nucypher.policy.conditions.utils import ConditionProviderManager


class ContextVariableCondition(Condition):
    CONDITION_TYPE = ConditionType.CONTEXT_VARIABLE.value

    class Schema(Condition.Schema):
        condition_type = fields.Str(
            validate=validate.Equal(ConditionType.CONTEXT_VARIABLE.value), required=True
        )
        context_variable = fields.Str(required=True)
        return_value_test = fields.Nested(
            ReturnValueTest.Schema(), required=False, allow_none=True
        )

        # maintain field declaration ordering
        class Meta:
            ordered = True

        @validates("context_variable")
        def validate_context_variable(self, value):
            if not is_context_variable(value):
                raise ValidationError(
                    f"Invalid value for context variable; expected a context variable, but got '{value}'"
                )

        @validates_schema
        def validate_return_value_test_required(self, data, **kwargs):
            # returnValueTest is only optional inside ConditionVariable context
            # or when directly constructing via Python (not deserializing from user input)
            if self.context.get("in_condition_variable", False):
                return
            if self.context.get("direct_construction", False):
                return
            if data.get("return_value_test") is None:
                raise ValidationError(
                    "returnValueTest is required",
                    field_name="returnValueTest",
                )

        @post_load
        def make(self, data, **kwargs):
            return ContextVariableCondition(**data)

    def __init__(
        self,
        context_variable: str,
        return_value_test: Optional[ReturnValueTest] = None,
        condition_type: str = ConditionType.CONTEXT_VARIABLE.value,
        name: Optional[str] = None,
    ):
        self.context_variable = context_variable
        self.return_value_test = return_value_test

        super().__init__(condition_type=condition_type, name=name)

    def __repr__(self) -> str:
        r = f"{self.__class__.__name__}(contextVariable={self.context_variable})"
        return r

    def verify(
        self, providers: ConditionProviderManager, **context
    ) -> Tuple[bool, Any]:
        resolved_context_var = resolve_any_context_variables(
            param=self.context_variable, providers=providers, **context
        )

        if self.return_value_test is None:
            # No test defined - resolution success = condition success
            return True, resolved_context_var

        resolved_return_value_test = self.return_value_test.with_resolved_context(
            providers=providers, **context
        )

        eval_result = resolved_return_value_test.eval(resolved_context_var)  # test

        return eval_result, resolved_context_var
