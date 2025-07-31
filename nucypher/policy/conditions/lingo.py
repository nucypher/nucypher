import ast
import base64
import json
import operator as pyoperator
from enum import Enum
from hashlib import md5
from typing import Any, List, Optional, Tuple, Type, Union

from hexbytes import HexBytes
from marshmallow import (
    Schema,
    ValidationError,
    fields,
    post_load,
    pre_load,
    validate,
    validates,
    validates_schema,
)
from marshmallow.validate import OneOf, Range
from packaging.version import parse as parse_version

from nucypher.policy.conditions.base import (
    Condition,
    ExecutionCall,
    MultiCondition,
    _Serializable,
)
from nucypher.policy.conditions.context import (
    is_context_variable,
    resolve_any_context_variables,
)
from nucypher.policy.conditions.exceptions import (
    InvalidCondition,
    InvalidConditionLingo,
    ReturnValueEvaluationError,
)
from nucypher.policy.conditions.types import ConditionDict, Lingo
from nucypher.policy.conditions.utils import (
    CamelCaseSchema,
    ConditionProviderManager,
    check_and_convert_any_big_ints,
    check_and_convert_big_int_string_to_int,
)


class AnyField(fields.Field):
    """
    Catch all field for all data types received in JSON.
    However, `taco-web` will provide bigints as strings since typescript can't handle large
    numbers as integers, so those need converting to integers.
    """

    def _serialize(self, value, attr, obj, **kwargs):
        return value

    def _deserialize(self, value, attr, data, **kwargs):
        return check_and_convert_any_big_ints(value)


class AnyLargeIntegerField(fields.Int):
    """
    Integer field that also allows for big int values for large numbers
    to be provided from `taco-web`. BigInts will be used for integer values > MAX_SAFE_INTEGER.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def _deserialize(self, value, attr, data, **kwargs):
        if isinstance(value, str):
            value = check_and_convert_big_int_string_to_int(value)

        return super()._deserialize(value, attr, data, **kwargs)


class _ConditionField(fields.Dict):
    """Serializes/Deserializes Conditions to/from dictionaries"""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def _serialize(self, value, attr, obj, **kwargs):
        return value.to_dict()

    def _deserialize(self, value, attr, data, **kwargs):
        lingo_version = self.context.get("lingo_version")
        condition_data = value
        condition_class = ConditionLingo.resolve_condition_class(
            condition=condition_data, version=lingo_version
        )
        instance = condition_class.from_dict(condition_data)
        return instance


# CONDITION = TIME | CONTRACT | RPC | JSON_API | JSON_RPC | JWT | COMPOUND | SEQUENTIAL | IF_THEN_ELSE_CONDITION | ADDRESS_ALLOWLIST | ECDSA  | SIGNING_ATTRIBUTE | SIGNING_ABI_ATTRIBUTE
class ConditionType(Enum):
    """
    Defines the types of conditions that can be evaluated.
    """

    TIME = "time"
    CONTRACT = "contract"
    RPC = "rpc"
    JSONAPI = "json-api"
    JSONRPC = "json-rpc"
    JWT = "jwt"
    COMPOUND = "compound"
    SEQUENTIAL = "sequential"
    IF_THEN_ELSE = "if-then-else"
    ADDRESS_ALLOWLIST = "address-allowlist"
    ECDSA = "ecdsa"
    SIGNING_ATTRIBUTE = "signing-attribute"
    SIGNING_ABI_ATTRIBUTE = "signing-abi-attribute"

    @classmethod
    def values(cls) -> List[str]:
        return [condition.value for condition in cls]


class Operator(Enum):
    """
    Defines the logical operators that can be used in compound conditions.
    """

    AND = "and"
    OR = "or"
    NOT = "not"

    @classmethod
    def values(cls) -> List[str]:
        return [op.value for op in cls]


class CompoundCondition(MultiCondition):
    """
    A combination of two or more conditions connected by logical operators such as AND, OR, NOT.

    CompoundCondition grammar:
        OPERATOR = AND | OR | NOT

        COMPOUND_CONDITION = {
            "name": ...  (Optional)
            "conditionType": "compound",
            "operator": OPERATOR,
            "operands": [CONDITION*]
        }
    """

    AND_OPERATOR = Operator.AND.value
    OR_OPERATOR = Operator.OR.value
    NOT_OPERATOR = Operator.NOT.value

    OPERATORS = tuple(Operator.values())
    CONDITION_TYPE = ConditionType.COMPOUND.value

    @classmethod
    def _validate_operator_and_operands(
        cls,
        operator: str,
        operands: List[Condition],
    ):
        if operator not in cls.OPERATORS:
            raise ValidationError(
                field_name="operator", message=f"{operator} is not a valid operator"
            )

        num_operands = len(operands)
        if operator == cls.NOT_OPERATOR:
            if num_operands != 1:
                raise ValidationError(
                    field_name="operands",
                    message=f"Only 1 operand permitted for '{operator}' compound condition",
                )
        elif num_operands < 2:
            raise ValidationError(
                field_name="operands",
                message=f"Minimum of 2 operand needed for '{operator}' compound condition",
            )
        elif num_operands > cls.MAX_NUM_CONDITIONS:
            raise ValidationError(
                field_name="operands",
                message="Maximum of {cls.MAX_NUM_CONDITIONS} operands allowed for '{operator}' compound condition",
            )

    class Schema(Condition.Schema):
        condition_type = fields.Str(
            validate=validate.Equal(ConditionType.COMPOUND.value), required=True
        )
        operator = fields.Str(required=True)
        operands = fields.List(_ConditionField, required=True)

        # maintain field declaration ordering
        class Meta:
            ordered = True

        @validates_schema
        def validate_operator_and_operands(self, data, **kwargs):
            operator = data["operator"]
            operands = data["operands"]
            CompoundCondition._validate_operator_and_operands(operator, operands)
            CompoundCondition._validate_multi_condition_nesting(
                conditions=operands, field_name="operands"
            )

        @post_load
        def make(self, data, **kwargs):
            return CompoundCondition(**data)

    def __init__(
        self,
        operator: str,
        operands: List[Condition],
        condition_type: str = CONDITION_TYPE,
        name: Optional[str] = None,
    ):
        """
        COMPOUND_CONDITION = {
            "operator": OPERATOR,
            "operands": [CONDITION*]
        }
        """
        self.operator = operator
        self.operands = operands

        super().__init__(
            condition_type=condition_type,
            name=name,
        )

        self.id = md5(bytes(self)).hexdigest()[:6]

    def __repr__(self):
        return f"Operator={self.operator} (NumOperands={len(self.operands)}), id={self.id})"

    def verify(self, *args, **kwargs) -> Tuple[bool, Any]:
        values = []
        overall_result = True if self.operator == self.AND_OPERATOR else False
        for condition in self.operands:
            current_result, current_value = condition.verify(*args, **kwargs)
            values.append(current_value)
            if self.operator == self.AND_OPERATOR:
                overall_result = overall_result and current_result
                # short-circuit check
                if overall_result is False:
                    break
            elif self.operator == self.OR_OPERATOR:
                overall_result = overall_result or current_result
                # short-circuit check
                if overall_result is True:
                    break
            else:
                # NOT_OPERATOR
                return not current_result, current_value

        return overall_result, values

    @property
    def conditions(self):
        return self.operands


class OrCompoundCondition(CompoundCondition):
    def __init__(self, operands: List[Condition]):
        super().__init__(operator=self.OR_OPERATOR, operands=operands)


class AndCompoundCondition(CompoundCondition):
    def __init__(self, operands: List[Condition]):
        super().__init__(operator=self.AND_OPERATOR, operands=operands)


class NotCompoundCondition(CompoundCondition):
    def __init__(self, operand: Condition):
        super().__init__(operator=self.NOT_OPERATOR, operands=[operand])


_COMPARATOR_FUNCTIONS = {
    "==": pyoperator.eq,
    "!=": pyoperator.ne,
    ">": pyoperator.gt,
    "<": pyoperator.lt,
    "<=": pyoperator.le,
    ">=": pyoperator.ge,
    # currently only supports checking value in list and not sub-string/bytes comparisons
    "in": lambda item, container: pyoperator.contains(container, item),
    "!in": lambda item, container: pyoperator.not_(
        pyoperator.contains(container, item)
    ),
}


class ConditionVariable(_Serializable):
    class Schema(CamelCaseSchema):
        var_name = fields.Str(required=True)
        condition = _ConditionField(required=True)

        @post_load
        def make(self, data, **kwargs):
            return ConditionVariable(**data)

    def __init__(self, var_name: str, condition: Condition):
        self.var_name = var_name
        self.condition = condition


class SequentialCondition(MultiCondition):
    """
    A series of conditions that are evaluated in a specific order, where the result of one
    condition can be used in subsequent conditions.

    SequentialCondition grammar:
        CONDITION_VARIABLE = {
            "varName": STR,
            "condition": {
                CONDITION
            }
        }

        SEQUENTIAL_CONDITION = {
            "name": ...  (Optional)
            "conditionType": "sequential",
            "conditionVariables": [CONDITION_VARIABLE*]
        }
    """

    CONDITION_TYPE = ConditionType.SEQUENTIAL.value

    @classmethod
    def _gather_all_nested_condition_variables(
        cls, conditions: List[Condition]
    ) -> List[ConditionVariable]:
        """
        Gathers all nested sequential conditions from the condition variables.
        """
        condition_variables = []
        for condition in conditions:
            if isinstance(condition, SequentialCondition):
                condition_variables.extend(condition.condition_variables)
            elif isinstance(condition, MultiCondition):
                # recursively gather from nested multi-conditions
                nested_condition_variables = cls._gather_all_nested_condition_variables(
                    condition.conditions
                )
                condition_variables.extend(nested_condition_variables)

        return condition_variables

    @classmethod
    def _validate_condition_variables(
        cls,
        condition_variables: List[ConditionVariable],
    ):
        if not condition_variables or len(condition_variables) < 2:
            raise ValidationError(
                field_name="condition_variables",
                message="At least two conditions must be specified",
            )

        if len(condition_variables) > cls.MAX_NUM_CONDITIONS:
            raise ValidationError(
                field_name="condition_variables",
                message=f"Maximum of {cls.MAX_NUM_CONDITIONS} conditions are allowed",
            )

        all_condition_variables = list(condition_variables)
        # gather all nested condition variables
        all_condition_variables.extend(
            cls._gather_all_nested_condition_variables(
                [
                    condition_variable.condition
                    for condition_variable in condition_variables
                ]
            )
        )

        # check for duplicate var names across all sequential conditions
        var_names = set()
        for condition_variable in all_condition_variables:
            if condition_variable.var_name in var_names:
                raise ValidationError(
                    field_name="condition_variables",
                    message=f"Duplicate variable names are not allowed - {condition_variable.var_name}",
                )
            var_names.add(condition_variable.var_name)

    class Schema(Condition.Schema):
        condition_type = fields.Str(
            validate=validate.Equal(ConditionType.SEQUENTIAL.value), required=True
        )
        condition_variables = fields.List(
            fields.Nested(ConditionVariable.Schema(), required=True)
        )

        # maintain field declaration ordering
        class Meta:
            ordered = True

        @validates("condition_variables")
        def validate_condition_variables(self, value):
            SequentialCondition._validate_condition_variables(value)
            conditions = [cv.condition for cv in value]
            SequentialCondition._validate_multi_condition_nesting(
                conditions=conditions, field_name="condition_variables"
            )

        @post_load
        def make(self, data, **kwargs):
            return SequentialCondition(**data)

    def __init__(
        self,
        condition_variables: List[ConditionVariable],
        condition_type: str = CONDITION_TYPE,
        name: Optional[str] = None,
    ):
        self.condition_variables = condition_variables
        super().__init__(
            condition_type=condition_type,
            name=name,
        )

    def __repr__(self):
        r = f"{self.__class__.__name__}(num_condition_variables={len(self.condition_variables)})"
        return r

    # TODO - think about not dereferencing context but using a dict;
    #  may allows more freedom for params
    def verify(
        self, providers: ConditionProviderManager, **context
    ) -> Tuple[bool, Any]:
        values = []
        latest_success = False
        inner_context = dict(context)  # don't modify passed in context - use a copy
        # resolve variables
        for condition_variable in self.condition_variables:
            latest_success, result = condition_variable.condition.verify(
                providers=providers, **inner_context
            )
            values.append(result)
            if not latest_success:
                # short circuit due to failed condition
                break

            inner_context[f":{condition_variable.var_name}"] = result

        return latest_success, values

    @property
    def conditions(self):
        return [
            condition_variable.condition
            for condition_variable in self.condition_variables
        ]


class _ElseConditionField(fields.Field):
    """
    Serializes/Deserializes else conditions for IfThenElseCondition. This field represents either a
    Condition or a boolean value.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def _serialize(self, value, attr, obj, **kwargs):
        if isinstance(value, bool):
            return value

        return value.to_dict()

    def _deserialize(self, value, attr, data, **kwargs):
        if isinstance(value, bool):
            return value

        lingo_version = self.context.get("lingo_version")
        condition_data = value
        condition_class = ConditionLingo.resolve_condition_class(
            condition=condition_data, version=lingo_version
        )
        instance = condition_class.from_dict(condition_data)
        return instance


class IfThenElseCondition(MultiCondition):
    """
    A condition that represents simple if-then-else logic.

    IF_THEN_ELSE_CONDITION = {
        "conditionType": "if-then-else",
        "ifCondition": CONDITION,
        "thenCondition": CONDITION,
        "elseCondition": CONDITION | true | false,
    }
    """

    CONDITION_TYPE = ConditionType.IF_THEN_ELSE.value

    MAX_NUM_CONDITIONS = 3  # only ever max of 3 (if, then, else)

    class Schema(Condition.Schema):
        condition_type = fields.Str(
            validate=validate.Equal(ConditionType.IF_THEN_ELSE.value), required=True
        )
        if_condition = _ConditionField(required=True)
        then_condition = _ConditionField(required=True)
        else_condition = _ElseConditionField(required=True)

        # maintain field declaration ordering
        class Meta:
            ordered = True

        @staticmethod
        def _validate_nested_conditions(field_name, condition):
            IfThenElseCondition._validate_multi_condition_nesting(
                conditions=[condition],
                field_name=field_name,
            )

        @validates("if_condition")
        def validate_if_condition(self, value):
            self._validate_nested_conditions("if_condition", value)

        @validates("then_condition")
        def validate_then_condition(self, value):
            self._validate_nested_conditions("then_condition", value)

        @validates("else_condition")
        def validate_else_condition(self, value):
            if isinstance(value, Condition):
                self._validate_nested_conditions("else_condition", value)

        @post_load
        def make(self, data, **kwargs):
            return IfThenElseCondition(**data)

    def __init__(
        self,
        if_condition: Condition,
        then_condition: Condition,
        else_condition: Union[Condition, bool],
        condition_type: str = CONDITION_TYPE,
        name: Optional[str] = None,
    ):
        self.if_condition = if_condition
        self.then_condition = then_condition
        self.else_condition = else_condition
        super().__init__(condition_type=condition_type, name=name)

    def __repr__(self):
        r = (
            f"{self.__class__.__name__}("
            f"if={self.if_condition.__class__.__name__}, "
            f"then={self.then_condition.__class__.__name__}, "
            f"else={self.else_condition.__class__.__name__}"
            f")"
        )
        return r

    @property
    def conditions(self):
        values = [self.if_condition, self.then_condition]
        if isinstance(self.else_condition, Condition):
            values.append(self.else_condition)

        return values

    def verify(self, *args, **kwargs) -> Tuple[bool, Any]:
        values = []

        # if
        if_result, if_value = self.if_condition.verify(*args, **kwargs)
        values.append(if_value)

        # then
        if if_result:
            then_result, then_value = self.then_condition.verify(*args, **kwargs)
            values.append(then_value)
            return then_result, values

        # else
        if isinstance(self.else_condition, Condition):
            # actual condition
            else_result, else_value = self.else_condition.verify(*args, **kwargs)
        else:
            # boolean value
            else_result, else_value = self.else_condition, self.else_condition

        values.append(else_value)
        return else_result, values


class ReturnValueTest(_Serializable):
    class InvalidExpression(ValueError):
        pass

    COMPARATORS = tuple(_COMPARATOR_FUNCTIONS)

    class Schema(CamelCaseSchema):
        SKIP_VALUES = (None,)
        comparator = fields.Str(
            required=True,
            validate=OneOf(_COMPARATOR_FUNCTIONS, error="Not a permitted comparator"),
        )
        value = AnyField(
            allow_none=False, required=True
        )  # any valid type (excludes None)
        index = fields.Int(
            strict=True,
            required=False,
            validate=Range(
                min=0, error="Not a permitted index. Must be a an non-negative integer."
            ),
            allow_none=True,
        )

        @validates_schema
        def validate_comparator_and_value(self, data, **kwargs):
            value = data.get("value")
            if is_context_variable(value):
                return

            comparator = data.get("comparator")
            if comparator in ["in", "!in"] and not isinstance(value, list):
                raise ValidationError(
                    field_name="value",
                    message=f'"{type(value)}" is not a valid type for "{comparator}"; only list is allowed.',
                )

        @post_load
        def make(self, data, **kwargs):
            return ReturnValueTest(**data)

    def __init__(self, comparator: str, value: Any, index: int = None):
        if not is_context_variable(value):
            # adjust stored value to be JSON serializable
            if isinstance(value, (tuple, set)):
                value = list(value)
            if isinstance(value, bytes):
                value = HexBytes(value).hex()

            try:
                json.dumps(value)
            except TypeError:
                raise self.InvalidExpression(
                    f"No JSON serializable equivalent found for type {type(value)}"
                )

            # verify that value is valid, but don't set it here so as not to change the value;
            # it will be sanitized at eval time. Need to maintain serialization/deserialization
            # consistency
            self._sanitize_value(value)

        self.comparator = comparator
        self.value = value
        self.index = index

        try:
            self._validate()
        except ValueError as e:
            raise self.InvalidExpression(f"{e}")

    @classmethod
    def _sanitize_value(cls, value):
        try:
            return ast.literal_eval(str(value))
        except Exception:
            raise cls.InvalidExpression(f'"{value}" is not a permitted value.')

    @staticmethod
    def __handle_potential_bytes(data: Any) -> Any:
        return HexBytes(data).hex() if isinstance(data, bytes) else data

    def _process_data(self, data: Any, index: Optional[int]) -> Any:
        """
        If an index is specified, return the value at that index in the data if data is list-like.
        Otherwise, return the data.
        """
        processed_data = data

        # try to get indexed entry first
        if index is not None:
            if not isinstance(processed_data, (list, tuple)):
                raise ReturnValueEvaluationError(
                    f"Index: {index} and Value: {processed_data} are not compatible types."
                )
            try:
                processed_data = data[index]
            except IndexError:
                raise ReturnValueEvaluationError(
                    f"Index '{index}' not found in returned data."
                )

        if isinstance(processed_data, (list, tuple)):
            # convert any bytes in list to hex (include nested lists/tuples); no additional indexing
            processed_data = [
                self._process_data(data=item, index=None) for item in processed_data
            ]
            return processed_data

        # convert bytes to hex if necessary
        return self.__handle_potential_bytes(processed_data)

    def eval(self, data) -> bool:
        if is_context_variable(self.value):
            # programming error if we get here
            raise RuntimeError(
                f"Return value comparator contains an unprocessed context variable (value={self.value}) and is not valid "
                f"for condition evaluation."
            )

        processed_data = self._process_data(data, self.index)
        left_operand = self._sanitize_value(processed_data)

        comparator_function = _COMPARATOR_FUNCTIONS.get(self.comparator)
        if self.comparator in ["in", "!in"]:
            # sanitize all values in list
            sanitized_list = [self._sanitize_value(v) for v in self.value]
            right_operand = sanitized_list
        else:
            right_operand = self._sanitize_value(self.value)

        result = comparator_function(left_operand, right_operand)

        return result

    def with_resolved_context(
        self, providers: Optional[ConditionProviderManager] = None, **context
    ):
        value = resolve_any_context_variables(self.value, providers, **context)
        return ReturnValueTest(self.comparator, value=value, index=self.index)


class ConditionLingo(_Serializable):
    VERSION = "1.0.0"

    class Schema(Schema):
        version = fields.Str(required=True)
        condition = _ConditionField(required=True)

        # maintain field declaration ordering
        class Meta:
            ordered = True

        @validates("version")
        def validate_version(self, version):
            ConditionLingo.check_version_compatibility(version)

        @pre_load
        def set_lingo_version(self, data, **kwargs):
            version = data.get("version")
            self.context["lingo_version"] = version
            return data

        @post_load
        def make(self, data, **kwargs):
            return ConditionLingo(**data)

    """
    A Collection of access control conditions evaluated as a compound boolean expression.

    This is an alternate implementation of the condition expression format used in
    the Lit Protocol (https://github.com/LIT-Protocol); credit to the authors for inspiring this work.
    """

    def __init__(self, condition: Condition, version: str = VERSION):
        self.condition = condition
        self.check_version_compatibility(version)
        self.version = version
        self.id = md5(bytes(self)).hexdigest()[:6]

    @classmethod
    def from_dict(cls, data: Lingo) -> "ConditionLingo":
        try:
            return super().from_dict(data)
        except ValidationError as e:
            raise InvalidConditionLingo(f"Invalid condition grammar: {e}")

    @classmethod
    def from_json(cls, data: str) -> 'ConditionLingo':
        try:
            return super().from_json(data)
        except ValidationError as e:
            raise InvalidConditionLingo(f"Invalid condition grammar: {e}")

    def to_base64(self) -> bytes:
        data = base64.b64encode(self.to_json().encode("utf-8"))
        return data

    @classmethod
    def from_base64(cls, data: bytes) -> "ConditionLingo":
        decoded_json = base64.b64decode(data).decode("utf-8")
        instance = cls.from_json(decoded_json)
        return instance

    def __bytes__(self) -> bytes:
        data = self.to_json().encode("utf-8")
        return data

    @classmethod
    def from_bytes(cls, data: bytes) -> "ConditionLingo":
        json_payload = data.decode("utf-8")
        instance = cls.from_json(json_payload)
        return instance

    def __repr__(self):
        return f"{self.__class__.__name__} (version={self.version} | id={self.id} | size={len(bytes(self))}) | condition=({self.condition})"

    def eval(self, *args, **kwargs) -> bool:
        result, _ = self.condition.verify(*args, **kwargs)
        return result

    @classmethod
    def resolve_condition_class(
        cls, condition: ConditionDict, version: int = None
    ) -> Type[Condition]:
        """
        Inspects a given block of JSON and attempts to resolve it's intended datatype within the
        conditions expression framework.
        """
        from nucypher.policy.conditions.address import AddressAllowlistCondition
        from nucypher.policy.conditions.ecdsa import ECDSACondition
        from nucypher.policy.conditions.evm import ContractCondition, RPCCondition
        from nucypher.policy.conditions.json.api import JsonApiCondition
        from nucypher.policy.conditions.json.rpc import JsonRpcCondition
        from nucypher.policy.conditions.jwt import JWTCondition
        from nucypher.policy.conditions.signing.base import (
            SigningObjectAbiAttributeCondition,
            SigningObjectAttributeCondition,
        )
        from nucypher.policy.conditions.time import TimeCondition

        # version logical adjustments can be made here as required

        condition_type = condition.get("conditionType")
        for condition in (
            TimeCondition,
            ContractCondition,
            RPCCondition,
            CompoundCondition,
            JsonApiCondition,
            JsonRpcCondition,
            JWTCondition,
            SequentialCondition,
            IfThenElseCondition,
            AddressAllowlistCondition,
            ECDSACondition,
            SigningObjectAttributeCondition,
            SigningObjectAbiAttributeCondition,
        ):
            if condition.CONDITION_TYPE == condition_type:
                return condition

        raise InvalidConditionLingo(
            f"Cannot resolve condition lingo, {condition}, with condition type {condition_type}"
        )

    @classmethod
    def check_version_compatibility(cls, version: str):
        if parse_version(version).major > parse_version(cls.VERSION).major:
            raise InvalidConditionLingo(
                f"Version provided, {version}, is incompatible with current version {cls.VERSION}"
            )


class ExecutionCallCondition(Condition):
    """
    Conditions that utilize underlying ExecutionCall objects.
    """

    EXECUTION_CALL_TYPE = NotImplemented

    class Schema(Condition.Schema):
        return_value_test = fields.Nested(ReturnValueTest.Schema(), required=True)

    def __init__(
        self,
        condition_type: str,
        return_value_test: ReturnValueTest,
        name: Optional[str] = None,
        *args,
        **kwargs,
    ):
        self.return_value_test = return_value_test

        try:
            self.execution_call = self.EXECUTION_CALL_TYPE(*args, **kwargs)
        except ExecutionCall.InvalidExecutionCall as e:
            raise InvalidCondition(str(e)) from e

        super().__init__(condition_type=condition_type, name=name)

    def verify(self, *args, **kwargs) -> Tuple[bool, Any]:
        """
        Verifies the condition is met by performing execution call and
        evaluating the return value test.
        """
        result = self.execution_call.execute(*args, **kwargs)

        resolved_return_value_test = self.return_value_test.with_resolved_context(
            **kwargs
        )
        eval_result = resolved_return_value_test.eval(result)  # test
        return eval_result, result
