from typing import Any, Optional, Tuple

from marshmallow import ValidationError, fields, post_load, validate, validates

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
        return_value_test = fields.Nested(ReturnValueTest.Schema(), required=True)

        # maintain field declaration ordering
        class Meta:
            ordered = True

        @validates("context_variable")
        def validate_context_variable(self, value):
            if not is_context_variable(value):
                raise ValidationError(
                    f"Invalid value for context variable; expected a context variable, but got '{value}'"
                )

        @post_load
        def make(self, data, **kwargs):
            return ContextVariableCondition(**data)

    def __init__(
        self,
        context_variable: str,
        return_value_test: ReturnValueTest,
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
        resolved_return_value_test = self.return_value_test.with_resolved_context(
            providers=providers, **context
        )

        resolved_context_var = resolve_any_context_variables(
            param=self.context_variable, providers=providers, **context
        )

        eval_result = resolved_return_value_test.eval(resolved_context_var)  # test

        return eval_result, resolved_context_var
