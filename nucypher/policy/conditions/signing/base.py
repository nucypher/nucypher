from abc import ABC
from typing import Any, Optional, Tuple

from marshmallow import fields, post_load, validate

from nucypher.policy.conditions.base import Condition
from nucypher.policy.conditions.context import (
    resolve_any_context_variables,
)
from nucypher.policy.conditions.exceptions import (
    InvalidContextVariableData,
)
from nucypher.policy.conditions.lingo import ConditionType, ReturnValueTest
from nucypher.policy.conditions.utils import ConditionProviderManager

SIGNING_CONDITION_OBJECT_CONTEXT_VAR = ":signingConditionObject"


class SigningObjectCondition(Condition, ABC):
    """
    Base class for signing conditions.
    This class is abstract and should not be instantiated directly.
    """

    class Schema(Condition.Schema):
        signing_object_context_var = fields.Str(
            required=True, validate=validate.Equal(SIGNING_CONDITION_OBJECT_CONTEXT_VAR)
        )

    def __init__(
        self,
        signing_object_context_var: str = SIGNING_CONDITION_OBJECT_CONTEXT_VAR,
        *args,
        **kwargs,
    ):
        self.signing_object_context_var = signing_object_context_var
        super().__init__(*args, **kwargs)


class SigningObjectAttributeCondition(SigningObjectCondition):
    CONDITION_TYPE = ConditionType.ATTRIBUTE.value

    class Schema(SigningObjectCondition.Schema):
        condition_type = fields.Str(
            validate=validate.Equal(ConditionType.ATTRIBUTE.value), required=True
        )
        attribute_name = fields.String(required=True)
        return_value_test = fields.Nested(ReturnValueTest.Schema(), required=True)

        # maintain field declaration ordering
        class Meta:
            ordered = True

        @post_load
        def make(self, data, **kwargs):
            return SigningObjectAttributeCondition(**data)

    def __init__(
        self,
        attribute_name: str,
        return_value_test: ReturnValueTest,
        signing_object_context_var: str = SIGNING_CONDITION_OBJECT_CONTEXT_VAR,
        condition_type: str = ConditionType.ATTRIBUTE.value,
        name: Optional[str] = None,
    ):
        self.attribute_name = attribute_name
        self.return_value_test = return_value_test
        super().__init__(
            signing_object_context_var=signing_object_context_var,
            condition_type=condition_type,
            name=name,
        )

    def verify(
        self, providers: ConditionProviderManager, **context
    ) -> Tuple[bool, Any]:
        resolved_return_value_test = self.return_value_test.with_resolved_context(
            providers=providers, **context
        )

        signing_object = resolve_any_context_variables(
            self.signing_object_context_var, providers=providers, **context
        )

        try:
            # TODO for EIP191SignatureRequest, the object is just bytes, so that would fail here
            #  how do we handle that?
            attribute_value = getattr(signing_object, self.attribute_name)
        except AttributeError:
            # makes it clear that entry not present - allows possibility that
            # attribute value could be None as a legit value
            raise InvalidContextVariableData(
                f"Object of type {type(signing_object)} provided does not have attribute {self.attribute_name}"
            )

        # TODO: not the cleanest way to handle a string value needing to be quoted
        #  for evaluation checking
        modified_attribute_value_to_check = attribute_value
        if isinstance(modified_attribute_value_to_check, str):
            if not modified_attribute_value_to_check.startswith("0x"):
                # value needs to be double-quoted
                modified_attribute_value_to_check = (
                    f'"{modified_attribute_value_to_check}"'
                )

        result = resolved_return_value_test.eval(modified_attribute_value_to_check)
        return result, attribute_value
