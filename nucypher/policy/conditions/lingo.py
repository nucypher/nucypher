import ast
import base64
import json
import math
import operator as pyoperator
import statistics
from decimal import Decimal, InvalidOperation, localcontext
from enum import Enum
from hashlib import md5
from inspect import signature
from typing import Any, List, Optional, Tuple, Type, Union

from eth_utils import is_hexstr, keccak, to_checksum_address
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
    ConditionEvaluationFailed,
    InvalidCondition,
    InvalidConditionLingo,
    ReturnValueEvaluationError,
)
from nucypher.policy.conditions.types import ConditionDict, Lingo
from nucypher.policy.conditions.utils import (
    CamelCaseSchema,
    ConditionProviderManager,
    _convert_any_decimals_to_floats,
    _convert_any_floats_to_decimal,
    _eth_to_wei,
    _to_token_base_units,
    _wei_to_eth,
    check_and_convert_any_big_ints,
    check_and_convert_big_int_string_to_int,
    extract_condition_failure_details,
)
from nucypher.utilities.logging import Logger


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


# CONDITION = TIME | CONTRACT | RPC | JSON | JSON_API | JSON_RPC | JWT | COMPOUND | SEQUENTIAL | IF_THEN_ELSE_CONDITION | ECDSA  | SIGNING_ATTRIBUTE | SIGNING_ABI_ATTRIBUTE
class ConditionType(Enum):
    """
    Defines the types of conditions that can be evaluated.
    """

    TIME = "time"
    CONTRACT = "contract"
    RPC = "rpc"
    JSON = "json"
    JSONAPI = "json-api"
    JSONRPC = "json-rpc"
    JWT = "jwt"
    COMPOUND = "compound"
    SEQUENTIAL = "sequential"
    IF_THEN_ELSE = "if-then-else"
    ECDSA = "ecdsa"
    SIGNING_ATTRIBUTE = "signing-attribute"
    SIGNING_ABI_ATTRIBUTE = "signing-abi-attribute"
    CONTEXT_VARIABLE = "context-variable"

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
    AT_LEAST = "at-least"

    @classmethod
    def values(cls) -> List[str]:
        return [op.value for op in cls]


class CompoundCondition(MultiCondition):
    """
    A combination of two or more conditions connected by logical operators such as AND, OR, NOT.

    CompoundCondition grammar:
        OPERATOR = AND | OR | NOT | AT_LEAST

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
    AT_LEAST_OPERATOR = Operator.AT_LEAST.value

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
                message=f"Maximum of {cls.MAX_NUM_CONDITIONS} operands allowed for '{operator}' compound condition",
            )

    class Schema(Condition.Schema):
        condition_type = fields.Str(
            validate=validate.Equal(ConditionType.COMPOUND.value), required=True
        )
        operator = fields.Str(required=True)
        operands = fields.List(_ConditionField, required=True)
        threshold = fields.Int(required=False)

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

            threshold = data.get("threshold", None)
            if operator == CompoundCondition.AT_LEAST_OPERATOR:
                number_of_operands = len(operands)
                if threshold is None:
                    raise ValidationError(
                        field_name="threshold",
                        message=f"Threshold must be specified for {operator} operator",
                    )
                elif threshold < 1 or threshold > number_of_operands:
                    raise ValidationError(
                        field_name="threshold",
                        message=f"Threshold must be between 1 and number of operands ({number_of_operands})",
                    )
            elif threshold is not None:
                raise ValidationError(
                    field_name="threshold",
                    message=f"Threshold is only valid for {CompoundCondition.AT_LEAST_OPERATOR} operator",
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
        threshold: Optional[int] = None,
    ):
        """
        COMPOUND_CONDITION = {
            "operator": OPERATOR,
            "operands": [CONDITION*]
        }
        """
        self.operator = operator
        self.operands = operands
        self.threshold = threshold

        super().__init__(
            condition_type=condition_type,
            name=name,
        )

        self.id = md5(bytes(self)).hexdigest()[:6]

    def __repr__(self):
        return f"Operator={self.operator} (NumOperands={len(self.operands)}), id={self.id})"

    def verify(self, *args, **kwargs) -> Tuple[bool, Any]:
        if self.operator == self.NOT_OPERATOR:
            current_result, current_value = self.operands[0].verify(*args, **kwargs)
            return not current_result, current_value

        values = []
        num_passed_conditions = 0
        overall_result = True if self.operator == self.AND_OPERATOR else False
        for condition in self.operands:
            current_result, current_value = condition.verify(*args, **kwargs)
            values.append(current_value)
            if current_result:
                num_passed_conditions += 1

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
            elif self.operator == self.AT_LEAST_OPERATOR:
                overall_result = num_passed_conditions >= self.threshold
                # short-circuit check
                if overall_result is True:
                    break

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


class AtLeastCompoundCondition(CompoundCondition):
    def __init__(self, operands: List[Condition], threshold: int):
        super().__init__(
            operator=self.AT_LEAST_OPERATOR, operands=operands, threshold=threshold
        )


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


def _to_hex(value):
    """
    Convert value to hex string.

    Supports bytes, bytearray, int, and str types.
    Strings are encoded to UTF-8 before conversion.

    :param value: Value to convert to hex
    :return: Hex string with 0x prefix
    :raises TypeError: If value type cannot be converted to hex
    """
    try:
        if isinstance(value, str):
            # Encode regular strings to UTF-8
            value = value.encode("utf-8")
        # HexBytes handles bytes, bytearray, and int
        h = HexBytes(value)
        return h.hex()
    except (TypeError, ValueError) as e:
        raise TypeError(f"Invalid value for hex conversion: {e}")


def _compute_create2_address(salt: bytes, value: dict) -> str:
    """
    Compute CREATE2 address locally.

    Formula: keccak256(0xff ++ deployer ++ salt ++ bytecode_hash)[12:]

    :param salt: The salt value (must be 32 bytes)
    :param value: Dict containing 'deployerAddress' and 'bytecodeHash'
    :return: Checksummed Ethereum address
    :raises TypeError: If inputs are invalid
    """
    try:
        deployer_address = value["deployerAddress"]
        bytecode_hash = value["bytecodeHash"]
    except (KeyError, TypeError) as e:
        raise TypeError(
            f"create2 operation requires dictionary with 'deployerAddress' and 'bytecodeHash' values: {e}"
        )

    # Validate and convert deployer address
    try:
        deployer_bytes = HexBytes(deployer_address)
    except Exception as e:
        raise TypeError(f"Invalid deployerAddress: {e}")
    if len(deployer_bytes) != 20:
        raise TypeError(f"deployerAddress must be 20 bytes, got {len(deployer_bytes)}")

    # Validate and convert salt
    try:
        salt_bytes = HexBytes(salt)
    except Exception as e:
        raise TypeError(f"Invalid salt: {e}")
    if len(salt_bytes) != 32:
        raise TypeError(f"salt must be 32 bytes, got {len(salt_bytes)}")

    # Validate and convert bytecode hash
    try:
        bytecode_hash_bytes = HexBytes(bytecode_hash)
    except Exception as e:
        raise TypeError(f"Invalid bytecodeHash: {e}")
    if len(bytecode_hash_bytes) != 32:
        raise TypeError(
            f"bytecodeHash must be 32 bytes, got {len(bytecode_hash_bytes)}"
        )

    # CREATE2: keccak256(0xff ++ deployer ++ salt ++ bytecode_hash)[12:]
    pre_image = b"\xff" + deployer_bytes + salt_bytes + bytecode_hash_bytes
    address_bytes = keccak(pre_image)[12:]

    return to_checksum_address(address_bytes)


# should raise TypeError for invalid inputs
_OPERATOR_FUNCTIONS = {
    # We can add all kinds of operators over time, this is just a base start - given that
    # we need ethToWei and weiToEth.
    # Whether this set is too aggressive or not remains to be seen. We can always pare
    # back on the operators we want to start with.
    "+=": pyoperator.add,
    "-=": pyoperator.sub,
    "*=": pyoperator.mul,
    "/=": pyoperator.truediv,
    "%=": pyoperator.mod,
    "index": lambda a, b: a[b],
    "round": lambda a, b: round(a, b),
    "toTokenBaseUnits": _to_token_base_units,
    # unary operations i.e. don't require 2nd 'b' value to be passed;
    "abs": lambda a: abs(a),
    "avg": lambda a: statistics.mean(a),
    "ceil": lambda a: math.ceil(a),
    "ethToWei": _eth_to_wei,
    "floor": lambda a: math.floor(a),
    "len": lambda a: len(a),
    "max": lambda a: max(a),
    "min": lambda a: min(a),
    "sum": lambda a: sum(a),
    "weiToEth": _wei_to_eth,
    # casting
    "bool": lambda a: bool(a),
    "float": lambda a: float(a),
    "int": lambda a: int(a),
    "str": lambda a: str(a),
    # JSON conversion
    "fromJson": lambda a: json.loads(a),
    "toJson": lambda a: json.dumps(a),
    # hex conversion
    "fromHex": lambda a: bytes(HexBytes(a)),
    "toHex": _to_hex,
    # hashing
    "keccak": lambda a: keccak(a.encode() if isinstance(a, str) else a),
    # address computation
    "create2": _compute_create2_address,
}

MAX_VARIABLE_OPERATIONS = 5


class VariableOperation(_Serializable):
    """
    An operation to be performed on a variable value.

    Evaluation of VariableOperation should always be done via `evaluate_operations()` to ensure
    floating precision if utilized is always maintained, even for evaluation of single operation.
    `_evaluate()` should never be called directly.

    There is a limit to floating point precision for operations.
    """

    class Schema(CamelCaseSchema):
        operation = fields.Str(
            required=True,
            validate=OneOf(_OPERATOR_FUNCTIONS, error="Not a permitted operation"),
        )
        value = AnyField(required=False, allow_none=True)

        @validates_schema
        def validate_operation_and_value(self, data, **kwargs):
            operation = data["operation"]
            value = data.get("value")
            if VariableOperation._is_unary_operation(operation):
                if value is not None:
                    raise ValidationError(
                        field_name="value",
                        message=f'No value should be provided for operation "{operation}"',
                    )
            elif value is None:
                raise ValidationError(
                    field_name="value",
                    message=f'A value must be provided for operation "{operation}"',
                )

        @post_load
        def make(self, data, **kwargs):
            return VariableOperation(**data)

    def __init__(self, operation: str, value: Any = None):
        self.operation = operation
        # don't convert value in constructor since serialization used for validation
        self.value = value

        super().__init__()
        self._validate()

    @classmethod
    def _is_unary_operation(cls, operation: str) -> bool:
        operation_fn = _OPERATOR_FUNCTIONS[operation]
        return len(signature(operation_fn).parameters) == 1

    def _evaluate(self, variable_value: Any):
        """
        Calculates the result of the operation on the variable value.

        This should never be called directly; use `evaluate_operations()` instead.
        """
        operation_function = _OPERATOR_FUNCTIONS[self.operation]
        if self._is_unary_operation(self.operation):
            return operation_function(variable_value)
        else:
            # convert value
            op_parameter = _convert_any_floats_to_decimal(self.value)
            return operation_function(variable_value, op_parameter)

    @classmethod
    def evaluate_operations(
        cls, operations: List["VariableOperation"], variable_value: Any
    ):
        """
        Calculates the result of a list of operations on the variable value.
        """
        if len(operations) < 1:
            raise ValueError(
                "At least one operation is required to perform calculations"
            )

        with localcontext() as ctx:
            # large precision to avoid any float precision issues during calcs
            # (same used for wei conversion)
            ctx.prec = 999

            # convert initial variable value to decimal if float
            result = _convert_any_floats_to_decimal(variable_value)
            for operation in operations:
                result = operation._evaluate(result)

        return _convert_any_decimals_to_floats(result)

    @classmethod
    def with_resolved_context(
        cls,
        operations: List["VariableOperation"],
        providers: ConditionProviderManager = None,
        **context,
    ):
        resolved_operations = []
        for operation in operations:
            resolved_value = (
                resolve_any_context_variables(
                    operation.value, providers=providers, **context
                )
                if operation.value is not None
                else None
            )
            resolved_operations.append(
                VariableOperation(operation=operation.operation, value=resolved_value)
            )
        return resolved_operations


class ConditionVariable(_Serializable):
    class Schema(CamelCaseSchema):
        var_name = fields.Str(required=True)
        condition = _ConditionField(required=True)
        operations = fields.List(
            fields.Nested(VariableOperation.Schema()),
            validate=[
                validate.Length(min=1, error="At least one operation required"),
                validate.Length(
                    max=MAX_VARIABLE_OPERATIONS,
                    error=f"Maximum of {MAX_VARIABLE_OPERATIONS} operations allowed",
                ),
            ],
            required=False,
        )

        @post_load
        def make(self, data, **kwargs):
            return ConditionVariable(**data)

    def __init__(
        self,
        var_name: str,
        condition: Condition,
        operations: Optional[List[VariableOperation]] = None,
    ):
        self.var_name = var_name
        self.condition = condition
        self.operations = operations

        self._validate()


class SequentialCondition(MultiCondition):
    MAX_NUM_CONDITIONS = 20

    """
    A series of conditions that are evaluated in a specific order, where the result of one
    condition can be used in subsequent conditions.

    SequentialCondition grammar:
        CONDITION_VARIABLE = {
            "varName": STR,
            "condition": {
                CONDITION
            }
            "operations": [VARIABLE_OPERATION*] (Optional)
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

            if condition_variable.operations:
                resolved_operations = VariableOperation.with_resolved_context(
                    condition_variable.operations, providers=providers, **inner_context
                )
                try:
                    result = VariableOperation.evaluate_operations(
                        resolved_operations, result
                    )
                except Exception as e:
                    raise ConditionEvaluationFailed(
                        f"Error performing operations on result of condition variable "
                        f"'{condition_variable.var_name}': {e}"
                    )

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

        # then condition not executed
        values.append(None)

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
        operations = fields.List(
            fields.Nested(VariableOperation.Schema()),
            validate=[
                validate.Length(min=1, error="At least one operation required"),
                validate.Length(
                    max=MAX_VARIABLE_OPERATIONS,
                    error=f"Maximum of {MAX_VARIABLE_OPERATIONS} operations allowed",
                ),
            ],
            required=False,
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

    def __init__(
        self,
        comparator: str,
        value: Any,
        index: Optional[int] = None,
        operations: Optional[List[VariableOperation]] = None,
    ):
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
        self.operations = operations

        try:
            self._validate()
        except ValueError as e:
            raise self.InvalidExpression(f"{e}")

    @classmethod
    def _sanitize_value(cls, value) -> Any:
        try:
            return ast.literal_eval(str(value))
        except Exception:
            raise cls.InvalidExpression(f'"{value}" is not a permitted value.')

    @staticmethod
    def __process_bytes(data: bytes) -> str:
        return HexBytes(data).hex()  # convert bytes to hex string

    @staticmethod
    def __string_already_primitive_type(data: str) -> bool:
        # check if boolean string
        if data in ["True", "False"]:
            return True

        # check if int or float as string
        try:
            _ = Decimal(data)
            return True
        except InvalidOperation:
            pass

        return False

    @staticmethod
    def __process_string(data: str) -> str:
        # if 0x prefixed hex string, leave as is
        if data.startswith("0x") and is_hexstr(data):
            return data
        # check if string is already primitive type, leave as is
        elif ReturnValueTest.__string_already_primitive_type(data):
            return data
        # check if already quoted; if not, quote it
        elif len(data) <= 1 or not (
            (data.startswith("'") and data.endswith("'"))
            or (data.startswith('"') and data.endswith('"'))
        ):
            quote_type_to_use = '"' if "'" in data else "'"
            return f"{quote_type_to_use}{data}{quote_type_to_use}"
        else:
            # leave as is
            return data

    def _process_data(self, data: Any, top_level_call: bool = True) -> Any:
        """
        Process data for use with literal eval. Recursively processes data as needed.
        Steps:
        1. Convert bytes to hex as needed, including within nested lists/tuples.
        2. Hex strings remain as is
        3. Strings that are already primitive types (int, float, bool) remain as is
        4. Convert non-hex strings to quoted strings at top level only i.e. individual string values
        (literal eval can only compare quoted strings); strings within data structures are fine
        """
        if isinstance(data, (list, tuple)):
            # convert any bytes in list to hex (include nested lists/tuples); no additional indexing
            processed_data = [
                self._process_data(data=item, top_level_call=False) for item in data
            ]
            return processed_data
        elif isinstance(data, bytes):
            # convert bytes to hex if necessary
            processed_data = self.__process_bytes(data)
            return processed_data
        elif isinstance(data, str):
            # only process strings at the top level call (i.e. don't need to process strings within lists/tuples)
            if not top_level_call:
                return data

            return self.__process_string(data)
        else:
            return data

    def eval(self, data) -> bool:
        if is_context_variable(self.value):
            # programming error if we get here
            raise RuntimeError(
                f"Return value comparator contains an unprocessed context variable (value={self.value}) and is not valid "
                f"for condition evaluation."
            )

        # check for index
        if self.index is not None:
            if not isinstance(data, (list, tuple)):
                raise ReturnValueEvaluationError(
                    f"Index: {self.index} and Value: {data} are not compatible types."
                )
            try:
                data = data[self.index]
            except IndexError:
                raise ReturnValueEvaluationError(
                    f"Index '{self.index}' not found in returned data."
                )

        # perform any additional operations before comparison
        if self.operations:
            try:
                data = VariableOperation.evaluate_operations(self.operations, data)
            except Exception as e:
                raise ReturnValueEvaluationError(
                    f"Error performing operations on returned data: {e}"
                )

        processed_data = self._process_data(data)
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
        resolved_value = resolve_any_context_variables(self.value, providers, **context)

        resolved_operations = None
        if self.operations:
            # make sure context variables are resolved for operations too
            resolved_operations = VariableOperation.with_resolved_context(
                self.operations, providers=providers, **context
            )

        return ReturnValueTest(
            self.comparator,
            value=resolved_value,
            index=self.index,
            operations=resolved_operations,
        )


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
        self.log = Logger(self.__class__.__name__)

    @classmethod
    def from_dict(cls, data: Lingo) -> "ConditionLingo":
        try:
            return super().from_dict(data)
        except ValidationError as e:
            raise InvalidConditionLingo(f"Invalid condition grammar: {e}")

    @classmethod
    def from_json(cls, data: str) -> "ConditionLingo":
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

    def eval(self, *args, debug_mode: bool = False, **kwargs) -> bool:
        result, value = self.condition.verify(*args, **kwargs)
        if not result and debug_mode:
            failure_details = extract_condition_failure_details(self.condition, value)
            debug_info = json.dumps(failure_details, indent=2, default=str)
            self.log.debug(
                f"Condition evaluation failed; ({self}). Debug info: {debug_info}"
            )

        return result

    @classmethod
    def resolve_condition_class(
        cls, condition: ConditionDict, version: int = None
    ) -> Type[Condition]:
        """
        Inspects a given block of JSON and attempts to resolve it's intended datatype within the
        conditions expression framework.
        """
        from nucypher.policy.conditions.ecdsa import ECDSACondition
        from nucypher.policy.conditions.evm import ContractCondition, RPCCondition
        from nucypher.policy.conditions.json.api import JsonApiCondition
        from nucypher.policy.conditions.json.json import JsonCondition
        from nucypher.policy.conditions.json.rpc import JsonRpcCondition
        from nucypher.policy.conditions.jwt import JWTCondition
        from nucypher.policy.conditions.signing.base import (
            SigningObjectAbiAttributeCondition,
            SigningObjectAttributeCondition,
        )
        from nucypher.policy.conditions.time import TimeCondition
        from nucypher.policy.conditions.var import ContextVariableCondition

        # version logical adjustments can be made here as required

        condition_type = condition.get("conditionType")
        for condition_class in (
            TimeCondition,
            ContractCondition,
            RPCCondition,
            CompoundCondition,
            ContextVariableCondition,
            JsonCondition,
            JsonApiCondition,
            JsonRpcCondition,
            JWTCondition,
            SequentialCondition,
            IfThenElseCondition,
            ECDSACondition,
            SigningObjectAttributeCondition,
            SigningObjectAbiAttributeCondition,
        ):
            if condition_class.CONDITION_TYPE == condition_type:
                return condition_class

        raise InvalidConditionLingo(
            f"Cannot resolve condition lingo, {condition_class}, with condition type {condition_type}"
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
