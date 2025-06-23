from abc import ABC
from typing import Any, Optional, Tuple

from marshmallow import (
    ValidationError,
    fields,
    post_load,
    validate,
    validates,
    validates_schema,
)
from marshmallow.validate import Range

from nucypher.policy.conditions.base import Condition
from nucypher.policy.conditions.context import (
    resolve_any_context_variables,
)
from nucypher.policy.conditions.exceptions import (
    InvalidContextVariableData,
)
from nucypher.policy.conditions.lingo import ConditionType, ReturnValueTest
from nucypher.policy.conditions.utils import (
    ConditionProviderManager,
    camel_case_to_snake,
    is_camel_case,
)
from nucypher.utilities.abi import (
    decode_human_readable_call,
    extract_arg_types,
    is_valid_human_readable_signature,
)

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
        attribute_name = fields.Str(required=True)
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
        # TODO what about camel case (from library) vs snake case (python) for
        #  attribute names (is this sufficient?)
        #  At the moment since there will be a python object, can we assume snake case conversion always?
        self.attribute_name = (
            camel_case_to_snake(attribute_name)
            # TODO should attribute name ever be a context variable? Likely not...
            if (attribute_name and is_camel_case(attribute_name))
            else attribute_name
        )
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

        raw_attribute_value, modified_attribute_value = self.get_attribute_value(
            signing_object
        )

        result = resolved_return_value_test.eval(modified_attribute_value)
        return result, raw_attribute_value

    def _get_raw_signing_object_attribute(self, signing_object: Any) -> Any:
        """
        Helper method to retrieve the attribute value from the signing object.
        Raises InvalidContextVariableData if the attribute does not exist.
        """
        try:
            # TODO for EIP191SignatureRequest, the object is just bytes, so that would fail here
            #  how do we handle that? Is raising the exception sufficient?
            raw_attribute_value = getattr(signing_object, self.attribute_name)
        except AttributeError:
            # makes it clear that entry not present - allows possibility that
            # attribute value could be None as a legit value
            raise InvalidContextVariableData(
                f"Object of type {type(signing_object)} provided does not have attribute {self.attribute_name}"
            )

        return raw_attribute_value

    @staticmethod
    def _adjust_for_attribute_string_value(attribute_value: Any) -> Any:
        """
        Adjusts the attribute value for evaluation checking.
        If the value is a string and does not start with '0x', it will be double-quoted.
        """
        if isinstance(attribute_value, str):
            if not attribute_value.startswith("0x"):
                # value needs to be double-quoted
                return f'"{attribute_value}"'

        return attribute_value

    def get_attribute_value(self, signing_object: Any) -> Tuple[Any, Any]:
        raw_attribute_value = self._get_raw_signing_object_attribute(signing_object)

        # TODO: not the cleanest way to handle a string value needing to be quoted
        #  for evaluation checking
        modified_attribute_value_to_check = self._adjust_for_attribute_string_value(
            raw_attribute_value
        )

        return raw_attribute_value, modified_attribute_value_to_check


class SigningObjectAbiAttributeCondition(SigningObjectAttributeCondition):
    CONDITION_TYPE = ConditionType.ABI_ATTRIBUTE.value

    class Schema(SigningObjectAttributeCondition.Schema):
        condition_type = fields.Str(
            validate=validate.Equal(ConditionType.ABI_ATTRIBUTE.value), required=True
        )
        abi_decode_string = fields.Str(required=True)
        abi_decode_value_index = fields.Int(validate=Range(min=0), required=True)

        @validates("abi_decode_string")
        def validate_abi_decode_string(self, value: str):
            if not is_valid_human_readable_signature(value):
                raise ValidationError(
                    f"Invalid ABI decode string: {value}. "
                    "Must be a valid human-readable signature."
                )

        @validates_schema
        def validate_abi_decode_value_index(self, data, **kwargs):
            abi_decode_value_index = data.get("abi_decode_value_index")
            abi_decode_string = data.get("abi_decode_string")

            arg_types = extract_arg_types(abi_decode_string)
            total_args_num = 1 + len(arg_types)  # method name + args
            if abi_decode_value_index >= total_args_num:
                raise ValidationError(
                    f"Value index '{abi_decode_value_index}' is out of range for "
                    f"the ABI decode string '{abi_decode_string}'. "
                )

        # maintain field declaration ordering
        class Meta:
            ordered = True

        @post_load
        def make(self, data, **kwargs):
            return SigningObjectAbiAttributeCondition(**data)

    def __init__(
        self,
        attribute_name: str,
        abi_decode_string: str,
        abi_decode_value_index: int,
        return_value_test: ReturnValueTest,
        signing_object_context_var: str = SIGNING_CONDITION_OBJECT_CONTEXT_VAR,
        condition_type: str = ConditionType.ABI_ATTRIBUTE.value,
        name: Optional[str] = None,
    ):
        self.abi_decode_string = abi_decode_string
        self.abi_decode_value_index = abi_decode_value_index

        super().__init__(
            attribute_name=attribute_name,
            return_value_test=return_value_test,
            signing_object_context_var=signing_object_context_var,
            condition_type=condition_type,
            name=name,
        )

    def get_attribute_value(self, signing_object: Any) -> Tuple[Any, Any]:
        raw_attribute_value = self._get_raw_signing_object_attribute(signing_object)
        method, args = decode_human_readable_call(
            self.abi_decode_string, raw_attribute_value
        )

        all_values = [method]
        all_values.extend(args)

        decoded_attribute_value_at_index = all_values[self.abi_decode_value_index]

        # adjust for string value
        modified_attribute_value_to_check = self._adjust_for_attribute_string_value(
            decoded_attribute_value_at_index
        )

        return decoded_attribute_value_at_index, modified_attribute_value_to_check
