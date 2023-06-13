import ast
import base64
import operator as pyoperator
from hashlib import md5
from typing import Any, List, Optional, Tuple

from marshmallow import Schema, ValidationError, fields, post_load, pre_load, validate

from nucypher.policy.conditions.base import AccessControlCondition, _Serializable
from nucypher.policy.conditions.context import is_context_variable
from nucypher.policy.conditions.exceptions import (
    InvalidConditionLingo,
    InvalidLogicalOperator,
    ReturnValueEvaluationError,
)
from nucypher.policy.conditions.types import ConditionDict, Lingo
from nucypher.policy.conditions.utils import CamelCaseSchema


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

#
# CONDITION = BASE_CONDITION | COMPOUND_CONDITION
#
# BASE_CONDITION = {
#     // ..
# }
#
# COMPOUND_CONDITION = {
#     "operator": OPERATOR,
#     "operands": [CONDITION*]
# }


class CompoundAccessControlCondition(AccessControlCondition):
    AND_OPERATOR = "and"
    OR_OPERATOR = "or"
    OPERATORS = (AND_OPERATOR, OR_OPERATOR)

    class Schema(CamelCaseSchema):
        SKIP_VALUES = (None,)
        name = fields.Str(required=False)
        operator = fields.Str(required=True, validate=validate.OneOf(["and", "or"]))
        operands = fields.List(
            _ConditionField, required=True, validate=validate.Length(min=2)
        )

        # maintain field declaration ordering
        class Meta:
            ordered = True

        @post_load
        def make(self, data, **kwargs):
            return CompoundAccessControlCondition(**data)

    def __init__(
        self,
        operator: str,
        operands: List[AccessControlCondition],
        name: Optional[str] = None,
    ):
        """
        COMPOUND_CONDITION = {
            "operator": OPERATOR,
            "operands": [CONDITION*]
        }
        """
        if operator not in self.OPERATORS:
            raise InvalidLogicalOperator(f"{operator} is not a valid operator")
        self.operator = operator
        self.operands = operands
        self.name = name
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
            else:
                # or operator
                overall_result = overall_result or current_result
                # short-circuit check
                if overall_result is True:
                    break

        return overall_result, values


class OrCompoundCondition(CompoundAccessControlCondition):
    def __init__(self, operands: List[AccessControlCondition]):
        super().__init__(operator=self.OR_OPERATOR, operands=operands)


class AndCompoundCondition(CompoundAccessControlCondition):
    def __init__(self, operands: List[AccessControlCondition]):
        super().__init__(operator=self.AND_OPERATOR, operands=operands)


class ReturnValueTest:
    class InvalidExpression(ValueError):
        pass

    _COMPARATOR_FUNCTIONS = {
        "==": pyoperator.eq,
        "!=": pyoperator.ne,
        ">": pyoperator.gt,
        "<": pyoperator.lt,
        "<=": pyoperator.le,
        ">=": pyoperator.ge,
    }
    COMPARATORS = tuple(_COMPARATOR_FUNCTIONS)

    class ReturnValueTestSchema(CamelCaseSchema):
        SKIP_VALUES = (None,)
        comparator = fields.Str(required=True)
        value = fields.Raw(
            allow_none=False, required=True
        )  # any valid type (excludes None)
        index = fields.Raw(allow_none=True)

        @post_load
        def make(self, data, **kwargs):
            return ReturnValueTest(**data)

    def __init__(self, comparator: str, value: Any, index: int = None):
        if comparator not in self.COMPARATORS:
            raise self.InvalidExpression(
                f'"{comparator}" is not a permitted comparator.'
            )

        if index is not None and not isinstance(index, int):
            raise self.InvalidExpression(
                f'"{index}" is not a permitted index. Must be a an integer.'
            )

        if not is_context_variable(value):
            # verify that value is valid, but don't set it here so as not to change the value;
            # it will be sanitized at eval time. Need to maintain serialization/deserialization
            # consistency
            self._sanitize_value(value)

        self.comparator = comparator
        self.value = value
        self.index = index

    def _sanitize_value(self, value):
        try:
            return ast.literal_eval(str(value))
        except Exception:
            raise self.InvalidExpression(f'"{value}" is not a permitted value.')

    def _process_data(self, data: Any) -> Any:
        """
        If an index is specified, return the value at that index in the data if data is list-like.
        Otherwise, return the data.
        """
        processed_data = data
        if self.index is not None:
            if isinstance(self.index, int) and isinstance(data, (list, tuple)):
                try:
                    processed_data = data[self.index]
                except IndexError:
                    raise ReturnValueEvaluationError(
                        f"Index '{self.index}' not found in return data."
                    )
            else:
                raise ReturnValueEvaluationError(
                    f"Index: {self.index} and Value: {data} are not compatible types."
                )

        return processed_data

    def eval(self, data) -> bool:
        if is_context_variable(self.value):
            # programming error if we get here
            raise RuntimeError(
                f"Return value comparator contains an unprocessed context variable (value={self.value}) and is not valid "
                f"for condition evaluation."
            )

        processed_data = self._process_data(data)
        left_operand = self._sanitize_value(processed_data)
        right_operand = self._sanitize_value(self.value)
        result = self._COMPARATOR_FUNCTIONS[self.comparator](left_operand, right_operand)
        return result


class ConditionLingo(_Serializable):
    VERSION = 1

    class Schema(Schema):
        version = fields.Int(required=True)  # TODO validation here
        condition = _ConditionField(required=True)

        # maintain field declaration ordering
        class Meta:
            ordered = True

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

    def __init__(self, condition: AccessControlCondition, version: int = VERSION):
        """
        CONDITION = BASE_CONDITION | COMPOUND_CONDITION
        BASE_CONDITION = {
                // ..
        }
        COMPOUND_CONDITION = {
                "operator": OPERATOR,
                "operands": [CONDITION*]
        }
        """
        self.condition = condition
        if version > self.VERSION:
            raise ValueError(
                f"Version provided is in the future {version} > {self.VERSION}"
            )
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
        data = base64.b64encode(self.to_json().encode())
        return data

    @classmethod
    def from_base64(cls, data: bytes) -> 'ConditionLingo':
        decoded_json = base64.b64decode(data).decode()
        instance = cls.from_json(decoded_json)
        return instance

    def __bytes__(self) -> bytes:
        data = self.to_json().encode()
        return data

    def __repr__(self):
        return f"{self.__class__.__name__} (version={self.version} | id={self.id} | size={len(bytes(self))}) | condition=({self.condition})"

    def eval(self, *args, **kwargs) -> bool:
        result, _ = self.condition.verify(*args, **kwargs)
        return result

    @classmethod
    def validate_condition_lingo(cls, lingo: Lingo):
        errors = cls.Schema().validate(data=lingo)
        if errors:
            raise InvalidConditionLingo(f"Invalid {cls.__name__}: {errors}")

    @classmethod
    def resolve_condition_class(
        cls, condition: ConditionDict, version: int = None
    ) -> Union[Type[CompoundAccessControlCondition], Type[AccessControlCondition]]:
        """
        TODO: This feels like a jenky way to resolve data types from JSON blobs, but it works.
        Inspects a given bloc of JSON and attempts to resolve it's intended  datatype within the
        conditions expression framework.
        """
        from nucypher.policy.conditions.evm import ContractCondition, RPCCondition
        from nucypher.policy.conditions.time import TimeCondition

        # version logical adjustments can be made here as required
        if version and version > ConditionLingo.VERSION:
            raise InvalidConditionLingo(
                f"Version is in the future: {version} > {ConditionLingo.VERSION}"
            )

        # Inspect
        method = condition.get("method")
        operator = condition.get("operator")
        contract = condition.get("contractAddress")

        # Resolve
        if method:
            if method == TimeCondition.METHOD:
                return TimeCondition
            elif contract:
                return ContractCondition
            # TODO this needs to be resolved (balanceof isn't actually allowed)
            #  also this should be a method on RPCCondition
            elif method.startswith(RPCCondition.ETH_PREFIX):
                return RPCCondition
        elif operator:
            return CompoundAccessControlCondition

        raise InvalidConditionLingo(
            f"Cannot resolve condition lingo type from data {condition}"
        )
