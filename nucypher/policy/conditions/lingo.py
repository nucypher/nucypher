import ast
import base64
import json
import operator as pyoperator
from hashlib import md5
from typing import Any, Dict, Iterator, List, Optional, Union

from marshmallow import fields, post_load

from nucypher.policy.conditions.base import ReencryptionCondition
from nucypher.policy.conditions.context import is_context_variable
from nucypher.policy.conditions.exceptions import (
    InvalidConditionLingo,
    InvalidLogicalOperator,
    ReturnValueEvaluationError,
)
from nucypher.policy.conditions.types import ConditionDict, LingoList
from nucypher.policy.conditions.utils import (
    CamelCaseSchema,
    deserialize_condition_lingo,
)


class Operator:
    OPERATORS = ("and", "or")
    _KEY = "operator"

    def __init__(self, _operator: str):
        if _operator not in self.OPERATORS:
            raise InvalidLogicalOperator(f"{_operator} is not a valid operator")
        self.operator = _operator

    def __str__(self) -> str:
        return self.operator

    def to_dict(self) -> Dict[str, str]:
        return {self._KEY: self.operator}

    @classmethod
    def from_dict(cls, data: ConditionDict) -> "Operator":
        cls.validate(data)
        instance = cls(_operator=data[cls._KEY])
        return instance

    @classmethod
    def from_json(cls, data) -> 'Operator':
        data = json.loads(data)
        instance = cls.from_dict(data)
        return instance

    def to_json(self) -> str:
        data = self.to_dict()
        data = json.dumps(data)
        return data

    @classmethod
    def validate(cls, data: ConditionDict) -> None:
        try:
            _operator = data[cls._KEY]  # underscore prefix to avoid name shadowing
        except KeyError:
            raise InvalidLogicalOperator(f"Invalid operator data: {data}")

        if _operator not in cls.OPERATORS:
            raise InvalidLogicalOperator(f"{_operator} is not a valid operator")


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
        key = fields.Raw(allow_none=True)

        @post_load
        def make(self, data, **kwargs):
            return ReturnValueTest(**data)

    def __init__(self, comparator: str, value: Any, key: Optional[Union[int, str]] = None):
        if comparator not in self.COMPARATORS:
            raise self.InvalidExpression(
                f'"{comparator}" is not a permitted comparator.'
            )

        if not isinstance(key, (int, str)) and key is not None:
            raise self.InvalidExpression(
                f'"{key}" is not a permitted key. Must be a string or integer.'
            )

        if not is_context_variable(value):
            # verify that value is valid, but don't set it here so as not to change the value;
            # it will be sanitized at eval time. Need to maintain serialization/deserialization
            # consistency
            self._sanitize_value(value)

        self.comparator = comparator
        self.value = value
        self.key = key

    def _sanitize_value(self, value):
        try:
            return ast.literal_eval(str(value))
        except Exception:
            raise self.InvalidExpression(f'"{value}" is not a permitted value.')

    def _process_data(self, data: Any) -> Any:
        """
        If a key is specified, return the value at that key in the data if data is a dict or list-like.
        Otherwise, return the data.
        """
        processed_data = data
        if self.key is not None:
            if isinstance(data, dict):
                try:
                    processed_data = data[self.key]
                except KeyError:
                    raise ReturnValueEvaluationError(
                        f"Key '{self.key}' not found in return data."
                    )
            elif isinstance(self.key, int) and isinstance(data, (list, tuple)):
                try:
                    processed_data = data[self.key]
                except IndexError:
                    raise ReturnValueEvaluationError(
                        f"Index '{self.key}' not found in return data."
                    )
            else:
                raise ReturnValueEvaluationError(
                    f"Key: {self.key} and Value: {data} are not compatible types."
                )

        return processed_data

    def eval(self, data) -> bool:
        if is_context_variable(self.value) or is_context_variable(self.key):
            # programming error if we get here
            raise RuntimeError(
                f"Return value comparator contains an unprocessed context variable (key={self.key}, value={self.value}) and is not valid "
                f"for condition evaluation."
            )

        processed_data = self._process_data(data)
        left_operand = self._sanitize_value(processed_data)
        right_operand = self._sanitize_value(self.value)
        result = self._COMPARATOR_FUNCTIONS[self.comparator](left_operand, right_operand)
        return result


class ConditionLingo:
    """
    A Collection of re-encryption conditions evaluated as a compound boolean expression.

    This is an alternate implementation of the condition expression format used in
    the Lit Protocol (https://github.com/LIT-Protocol); credit to the authors for inspiring this work.
    """

    def __init__(self, conditions: List[Union[ReencryptionCondition, Operator, Any]]):
        """
        The input list *must* be structured as follows:
        condition
        operator
        condition
        ...
        """
        self._validate_grammar(lingo=conditions)
        self.conditions = conditions
        self.id = md5(bytes(self)).hexdigest()[:6]

    @staticmethod
    def _validate_grammar(lingo) -> None:
        if len(lingo) % 2 == 0:
            raise InvalidConditionLingo(
                "conditions must be odd length, ever other element being an operator"
            )
        for index, element in enumerate(lingo):
            if (not index % 2) and not (isinstance(element, ReencryptionCondition)):
                raise InvalidConditionLingo(
                    f"{index} element must be a condition; Got {type(element)}."
                )
            elif (index % 2) and (not isinstance(element, Operator)):
                raise InvalidConditionLingo(
                    f"{index} element must be an operator; Got {type(element)}."
                )

    @classmethod
    def from_list(cls, payload: LingoList) -> "ConditionLingo":
        conditions = [deserialize_condition_lingo(c) for c in payload]
        instance = cls(conditions=conditions)
        return instance

    def to_list(self):  # TODO: __iter__ ?
        payload = [c.to_dict() for c in self.conditions]
        return payload

    def to_json(self) -> str:
        data = json.dumps(self.to_list())
        return data

    @classmethod
    def from_json(cls, data: str) -> 'ConditionLingo':
        data = json.loads(data)
        instance = cls.from_list(payload=data)
        return instance

    def to_base64(self) -> bytes:
        data = base64.b64encode(self.to_json().encode())
        return data

    @classmethod
    def from_base64(cls, data: bytes) -> 'ConditionLingo':
        data = base64.b64decode(data).decode()
        instance = cls.from_json(data)
        return instance

    def __bytes__(self) -> bytes:
        data = self.to_json().encode()
        return data

    def __repr__(self):
        return f"{self.__class__.__name__} (id={self.id} | size={len(bytes(self))})"

    def __eval(self, eval_string: str):
        # TODO: Additional protection and/or sanitation here
        result = eval(eval_string)
        return result

    def __process(self, *args, **kwargs) -> Iterator:
        # TODO: Prevent this lino from bein evaluated if this node does not have
        #       a connection to all the required blockchains (optimization)
        for task in self.conditions:
            if isinstance(task, ReencryptionCondition):
                condition = task
                result, value = condition.verify(*args, **kwargs)
                yield result
            elif isinstance(task, Operator):
                yield task
            else:
                raise InvalidConditionLingo(
                    f"Unrecognized type {type(task)} for ConditionLingo"
                )

    def eval(self, *args, **kwargs) -> bool:
        data = self.__process(*args, **kwargs)
        # [True, <Operator>, False] -> 'True or False'
        eval_string = ' '.join(str(e) for e in data)
        result = self.__eval(eval_string=eval_string)
        return result

OR = Operator('or')
AND = Operator('and')
