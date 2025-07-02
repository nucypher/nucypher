from abc import ABC
from typing import Any, Dict, List, Optional, Tuple

from marshmallow import (
    ValidationError,
    fields,
    post_load,
    validate,
    validates,
    validates_schema,
)
from marshmallow.validate import Range

from nucypher.policy.conditions.base import Condition, _Serializable
from nucypher.policy.conditions.context import (
    resolve_any_context_variables,
)
from nucypher.policy.conditions.exceptions import (
    InvalidCondition,
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
    CONDITION_TYPE = ConditionType.SIGNING_ATTRIBUTE.value

    class Schema(BaseSigningObjectAttributeCondition.Schema):
        condition_type = fields.Str(
            validate=validate.Equal(ConditionType.SIGNING_ATTRIBUTE.value),
            required=True,
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
        condition_type: str = ConditionType.SIGNING_ATTRIBUTE.value,
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


class AbiParameterValidation(_Serializable):
    class Schema(CamelCaseSchema):
        parameter_index = fields.Integer(validate=Range(min=0), required=True)

        index_within_tuple = fields.Integer(
            validate=Range(min=0), allow_none=True, required=False
        )

        # Either a direct comparator...
        return_value_test = fields.Nested(
            ReturnValueTest.Schema(), allow_none=True, required=False
        )

        # ...or a nested ABI call to decode and evaluate
        nested_abi_validation = fields.Nested(
            lambda: AbiCallValidation.Schema(), allow_none=True, required=False
        )

        # maintain field declaration ordering
        class Meta:
            ordered = True

        @validates_schema
        def validate_rtv_or_nested_validation(self, data, **kwargs):
            return_value_test = data.get("return_value_test")
            nested_abi_validation = data.get("nested_abi_validation")
            if not (bool(return_value_test) ^ bool(nested_abi_validation)):
                raise ValidationError(
                    "Either return value test or nested abi validation but not both."
                )

        @post_load
        def make(self, data, **kwargs):
            return AbiParameterValidation(**data)

    def __init__(
        self,
        parameter_index: int,
        index_within_tuple: Optional[int] = None,
        return_value_test: Optional[ReturnValueTest] = None,
        nested_abi_validation: Optional["AbiCallValidation"] = None,
    ):
        self.parameter_index = parameter_index
        self.index_within_tuple = index_within_tuple
        self.return_value_test = return_value_test
        self.nested_abi_validation = nested_abi_validation

        self._validate()

    def get_value(self, args):
        parameter_value = args[self.parameter_index]

        if self.index_within_tuple is not None:
            if not isinstance(parameter_value, tuple):
                raise ValueError(
                    f"Invalid data type for checking call data; expected tuple, received {type(parameter_value)}"
                )

            return parameter_value[self.index_within_tuple]

        return parameter_value

    def check(
        self, args: List[Any], providers: ConditionProviderManager, **context
    ) -> Tuple[bool, Any]:
        parameter_value = self.get_value(args)

        if self.return_value_test:
            resolved_return_value_test = self.return_value_test.with_resolved_context(
                providers=providers, **context
            )

            # adjust for string value
            modified_parameter_value_to_check = adjust_for_attribute_value_for_eval(
                parameter_value
            )

            result = resolved_return_value_test.eval(modified_parameter_value_to_check)
            return result, parameter_value
        else:
            result, value = self.nested_abi_validation.check(
                parameter_value, providers, **context
            )
            return result, value


class AbiCallValidation(_Serializable):
    class Schema(CamelCaseSchema):
        allowed_abi_calls = fields.Dict(
            keys=fields.Str(),
            values=fields.List(fields.Nested(AbiParameterValidation.Schema())),
            required=True,
        )

        @validates("allowed_abi_calls")
        def validate_allowed_abi_calls(
            self, value: Dict[str, List[AbiParameterValidation]]
        ):
            human_signatures = list(value.keys())
            if not human_signatures:
                raise ValidationError("At least one allowed abi call must be specified")

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

                    if parameter_value_check.index_within_tuple is not None:
                        tuple_args = arg_types[parameter_value_check.parameter_index]
                        if not (
                            tuple_args.startswith("(") and tuple_args.endswith(")")
                        ):
                            raise ValidationError(
                                f"Args value at index '{parameter_value_check.parameter_index}' is not a tuple"
                            )

                        tuple_args = tuple_args.strip("(").strip(")")
                        if parameter_value_check.index_within_tuple >= len(
                            tuple_args.split(",")
                        ):
                            raise ValidationError(
                                f"Tuple value index '{parameter_value_check.index_within_tuple}' for parameter is out of range for "
                                f"the ABI decoded tuple '{tuple_args}'. "
                            )

                    if parameter_value_check.nested_abi_validation:
                        # ensure that corresponding arg type is bytes
                        arg_type_to_check = arg_types[
                            parameter_value_check.parameter_index
                        ]
                        if parameter_value_check.index_within_tuple is not None:
                            tuple_args = arg_type_to_check.strip("(").strip(")")
                            arg_type_to_check = tuple_args.split(",")[
                                parameter_value_check.index_within_tuple
                            ]
                        if arg_type_to_check != "bytes":
                            raise ValidationError(
                                f"Nested ABI validation is only supported for bytes type, but found '{arg_type_to_check}'."
                            )

        @post_load
        def make(self, data, **kwargs):
            return AbiCallValidation(**data)

    def __init__(self, allowed_abi_calls: Dict[str, List[AbiParameterValidation]]):
        self.allowed_abi_calls = allowed_abi_calls

        self._validate()

    def check(
        self, value: Any, providers: ConditionProviderManager, **context
    ) -> Tuple[bool, Any]:
        if not isinstance(value, bytes):
            raise ValueError(
                f"Invalid data type for checking call data; expected bytes, received {type(value)}"
            )

        # check allowed signatures
        args = None
        matched_signature = None
        for allowed_signature in self.allowed_abi_calls:
            try:
                _, args = decode_human_readable_call(allowed_signature, value)
                matched_signature = allowed_signature
                # found a match
                break
            except ValueError:
                # signature doesn't match this call, try others in the list
                pass

        if not matched_signature:
            return False, []

        # TODO: not sure what to return as "values" (currently this includes calldata bytes which
        #  seems excessive)
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


class SigningObjectAbiAttributeCondition(BaseSigningObjectAttributeCondition):
    CONDITION_TYPE = ConditionType.SIGNING_ABI_ATTRIBUTE.value

    class Schema(BaseSigningObjectAttributeCondition.Schema):
        condition_type = fields.Str(
            validate=validate.Equal(ConditionType.SIGNING_ABI_ATTRIBUTE.value),
            required=True,
        )
        abi_validation = fields.Nested(AbiCallValidation.Schema(), required=True)

        # maintain field declaration ordering
        class Meta:
            ordered = True

        @post_load
        def make(self, data, **kwargs):
            return SigningObjectAbiAttributeCondition(**data)

    def __init__(
        self,
        attribute_name: str,
        abi_validation: AbiCallValidation,
        signing_object_context_var: str = SIGNING_CONDITION_OBJECT_CONTEXT_VAR,
        condition_type: str = ConditionType.SIGNING_ABI_ATTRIBUTE.value,
        name: Optional[str] = None,
    ):
        self.abi_validation = abi_validation
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

        try:
            result, values = self.abi_validation.check(
                raw_attribute_value, providers, **context
            )
            return result, values
        except ValueError as e:
            raise InvalidCondition(str(e))
