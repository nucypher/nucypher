from abc import ABC
from typing import Any, Dict, List, Optional, Tuple

from marshmallow import (
    ValidationError,
    fields,
    post_load,
    validate,
    validates,
)
from marshmallow.validate import Range

from nucypher.policy.conditions.base import Condition, _Serializable
from nucypher.policy.conditions.context import (
    resolve_any_context_variables,
)
from nucypher.policy.conditions.exceptions import (
    InvalidContextVariableData,
)
from nucypher.policy.conditions.lingo import ConditionType, ReturnValueTest
from nucypher.policy.conditions.signing.utils import adjust_for_attribute_value_for_eval
from nucypher.policy.conditions.utils import (
    CamelCaseSchema,
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

        class Meta:
            ordered = True

    def __init__(
        self,
        signing_object_context_var: str = SIGNING_CONDITION_OBJECT_CONTEXT_VAR,
        *args,
        **kwargs,
    ):
        self.signing_object_context_var = signing_object_context_var
        super().__init__(*args, **kwargs)


class BaseSigningObjectAttributeCondition(SigningObjectCondition, ABC):
    class Schema(SigningObjectCondition.Schema):
        attribute_name = fields.Str(required=True)

        # maintain field declaration ordering
        class Meta:
            ordered = True

    def __init__(
        self,
        attribute_name: str,
        *args,
        **kwargs,
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

        super().__init__(*args, **kwargs)

    def get_attribute_value(
        self, providers: ConditionProviderManager, **context
    ) -> Any:
        signing_object = resolve_any_context_variables(
            param=self.signing_object_context_var, providers=providers, **context
        )

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


class SigningObjectAttributeCondition(BaseSigningObjectAttributeCondition):
    CONDITION_TYPE = ConditionType.ATTRIBUTE.value

    class Schema(BaseSigningObjectAttributeCondition.Schema):
        condition_type = fields.Str(
            validate=validate.Equal(ConditionType.ATTRIBUTE.value), required=True
        )
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
        self.return_value_test = return_value_test
        super().__init__(
            attribute_name=attribute_name,
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

        raw_attribute_value = self.get_attribute_value(providers=providers, **context)

        # TODO: not the cleanest way to handle a string value needing to be quoted
        #  for evaluation checking
        modified_attribute_value_to_check = adjust_for_attribute_value_for_eval(
            raw_attribute_value
        )

        result = resolved_return_value_test.eval(modified_attribute_value_to_check)
        return result, raw_attribute_value


class AbiParameterValueCheck(_Serializable):
    class Schema(CamelCaseSchema):
        parameter_index = fields.Int(validate=Range(min=0), required=True)
        return_value_test = fields.Nested(ReturnValueTest.Schema(), required=True)

        @post_load
        def make(self, data, **kwargs):
            return AbiParameterValueCheck(**data)

    def __init__(self, parameter_index: int, return_value_test: ReturnValueTest):
        self.parameter_index = parameter_index
        self.return_value_test = return_value_test

        self._validate()

    def check(
        self, args: List[Any], providers: ConditionProviderManager, **context
    ) -> Tuple[bool, Any]:
        resolved_return_value_test = self.return_value_test.with_resolved_context(
            providers=providers, **context
        )

        parameter_value = args[self.parameter_index]
        # adjust for string value
        modified_parameter_value_to_check = adjust_for_attribute_value_for_eval(
            parameter_value
        )

        result = resolved_return_value_test.eval(modified_parameter_value_to_check)
        return result, parameter_value


class SigningObjectAbiAttributeCondition(BaseSigningObjectAttributeCondition):
    CONDITION_TYPE = ConditionType.ABI_ATTRIBUTE.value

    class Schema(BaseSigningObjectAttributeCondition.Schema):
        condition_type = fields.Str(
            validate=validate.Equal(ConditionType.ABI_ATTRIBUTE.value), required=True
        )
        allowed_abi_calls = fields.Dict(
            keys=fields.Str(),
            values=fields.List(fields.Nested(AbiParameterValueCheck.Schema())),
            required=True,
        )

        @validates("allowed_abi_calls")
        def validate_allowed_abi_calls(
            self, value: Dict[str, List[AbiParameterValueCheck]]
        ):
            human_signatures = value.keys()
            for human_signature in human_signatures:
                if not is_valid_human_readable_signature(human_signature):
                    raise ValidationError(
                        f"Invalid ABI signature: {human_signature}. "
                        "Must be a valid human-readable signature."
                    )

                arg_types = extract_arg_types(human_signature)
                total_args_num = len(arg_types)
                parameter_value_checks = value[human_signature]
                for parameter_value_check in parameter_value_checks:
                    if parameter_value_check.parameter_index >= total_args_num:
                        raise ValidationError(
                            f"Parameter value index '{parameter_value_check.parameter_index}' is out of range for "
                            f"the ABI decode string '{human_signature}'. "
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
        allowed_abi_calls: Dict[str, List[AbiParameterValueCheck]],
        signing_object_context_var: str = SIGNING_CONDITION_OBJECT_CONTEXT_VAR,
        condition_type: str = ConditionType.ABI_ATTRIBUTE.value,
        name: Optional[str] = None,
    ):
        self.allowed_abi_calls = allowed_abi_calls
        super().__init__(
            attribute_name=attribute_name,
            signing_object_context_var=signing_object_context_var,
            condition_type=condition_type,
            name=name,
        )

    def verify(
        self, providers: ConditionProviderManager, **context
    ) -> Tuple[bool, Any]:
        raw_attribute_value = self.get_attribute_value(providers=providers, **context)

        # check allowed signatures
        args = None
        matched_signature = None
        for allowed_signature in self.allowed_abi_calls:
            try:
                _, args = decode_human_readable_call(
                    allowed_signature, raw_attribute_value
                )
                matched_signature = allowed_signature
                # found a match
                break
            except ValueError:
                # signature doesn't match this call, try others in the list
                pass

        if not matched_signature:
            return False, []

        parameter_values = []
        additional_parameter_checks = self.allowed_abi_calls[matched_signature]
        if not additional_parameter_checks:
            # no additional checks to perform
            return True, matched_signature

        for parameter_check in additional_parameter_checks:
            result, raw_value = parameter_check.check(
                args=args, providers=providers, **context
            )
            parameter_values.append(raw_value)
            if not result:
                return False, parameter_values

        # if we get here additional checks have all passed
        return True, parameter_values
