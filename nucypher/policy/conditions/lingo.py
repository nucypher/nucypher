import ast
import base64
import json
import operator as pyoperator
from hashlib import md5
from typing import Any, List, Optional, Tuple

from marshmallow import fields, post_load, validate

from nucypher.policy.conditions.base import AccessControlCondition
from nucypher.policy.conditions.context import is_context_variable
from nucypher.policy.conditions.exceptions import (
    InvalidLogicalOperator,
    ReturnValueEvaluationError,
)
from nucypher.policy.conditions.types import Lingo
from nucypher.policy.conditions.utils import (
    CamelCaseSchema,
    deserialize_condition_lingo,
)


class _ConditionsField(fields.Dict):
    """Serializes/Deserializes Conditions to/from dictionaries"""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def _serialize(self, value, attr, obj, **kwargs):
        return value.to_dict()

    def _deserialize(self, value, attr, data, **kwargs):
        condition = deserialize_condition_lingo(value)
        return condition


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
            _ConditionsField, required=True, validate=validate.Length(min=2)
        )

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


class ConditionLingo:
    """
    A Collection of access control conditions evaluated as a compound boolean expression.

    This is an alternate implementation of the condition expression format used in
    the Lit Protocol (https://github.com/LIT-Protocol); credit to the authors for inspiring this work.
    """

    def __init__(self, condition: AccessControlCondition):
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
        self.id = md5(bytes(self)).hexdigest()[:6]

    def to_dict(self) -> Lingo:
        return self.condition.to_dict()

    @classmethod
    def from_dict(cls, data: Lingo) -> "ConditionLingo":
        condition = deserialize_condition_lingo(data)
        instance = cls(condition=condition)
        return instance

    def to_json(self) -> str:
        data = json.dumps(self.to_dict())
        return data

    @classmethod
    def from_json(cls, data: str) -> 'ConditionLingo':
        payload = json.loads(data)
        instance = cls.from_dict(data=payload)
        return instance

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
        return f"{self.__class__.__name__} (id={self.id} | size={len(bytes(self))}) | condition=({self.condition})"

    def eval(self, *args, **kwargs) -> bool:
        result, _ = self.condition.verify(*args, **kwargs)
        return result
