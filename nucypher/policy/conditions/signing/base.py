from typing import Any, Optional, Tuple

from marshmallow import ValidationError, fields, post_load, validate, validates

from nucypher.policy.conditions.base import Condition
from nucypher.policy.conditions.context import (
    is_context_variable,
    resolve_any_context_variables,
)
from nucypher.policy.conditions.exceptions import (
    InvalidContextVariableData,
    RequiredContextVariable,
)
from nucypher.policy.conditions.lingo import ConditionType, ReturnValueTest
from nucypher.policy.conditions.utils import ConditionProviderManager


class AttributeCondition(Condition):
    CONDITION_TYPE = ConditionType.ATTRIBUTE.value

    class Schema(Condition.Schema):
        condition_type = fields.Str(
            validate=validate.Equal(ConditionType.ATTRIBUTE.value), required=True
        )
        attribute_name = fields.String(required=True)
        object_context_var = fields.String(required=True)
        return_value_test = fields.Nested(
            ReturnValueTest.ReturnValueTestSchema(), required=True
        )

        # maintain field declaration ordering
        class Meta:
            ordered = True

        @validates("object_context_var")
        def validate_object_context_var(self, value):
            if not is_context_variable(value):
                raise ValidationError(
                    f"Invalid value for context variable; expected a context variable, but got '{value}'"
                )

        @post_load
        def make(self, data, **kwargs):
            return AttributeCondition(**data)

    def __init__(
        self,
        attribute_name: str,
        object_context_var: str,
        return_value_test: ReturnValueTest,
        condition_type: str = ConditionType.ATTRIBUTE.value,
        name: Optional[str] = None,
    ):
        self.attribute_name = attribute_name
        self.object_context_var = object_context_var
        self.return_value_test = return_value_test
        super().__init__(condition_type=condition_type, name=name)

    def verify(
        self, providers: ConditionProviderManager, **context
    ) -> Tuple[bool, Any]:
        resolved_return_value_test = self.return_value_test.with_resolved_context(
            providers=providers, **context
        )

        object_dict = resolve_any_context_variables(
            self.object_context_var, providers=providers, **context
        )
        if not object_dict:
            raise RequiredContextVariable(
                f"No object entry for context variable {self.object_context_var}"
            )

        if not isinstance(object_dict, dict):
            raise InvalidContextVariableData(
                f"Object provided for context var {self.object_context_var} is not a dictionary"
            )

        try:
            attribute_value = object_dict[self.attribute_name]
        except KeyError:
            # makes it clear that entry not present - allows possibility that
            # attribute value could be None as a legit value
            raise InvalidContextVariableData(
                f"Object provided for context var {self.object_context_var} does not have attribute {self.attribute_name}"
            )

        result = resolved_return_value_test.eval(attribute_value)
        return result, attribute_value
