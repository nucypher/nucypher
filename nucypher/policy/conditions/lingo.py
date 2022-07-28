import base64
import json
from marshmallow import fields, post_load
from typing import Union, Tuple, List, Dict, Any

from nucypher.policy.conditions._utils import CamelCaseSchema, _deserialize_condition_lingo
from nucypher.policy.conditions.base import ReencryptionCondition


class Operator:
    OPERATORS = ('and', 'or')

    def __init__(self, operator: str):
        if operator not in self.OPERATORS:
            raise Exception(f'{operator} is not a valid operator')
        self.operator = operator

    def __str__(self) -> str:
        return self.operator

    def to_dict(self) -> Dict[str, str]:
        return {'operator': self.operator}

    @classmethod
    def from_dict(cls, data: Dict[str, str]) -> 'Operator':
        try:
            operator = data['operator']
        except KeyError:
            raise Exception(f'Invalid operator JSON')
        instance = cls(operator=operator)
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


class ReturnValueTest:
    COMPARATORS = ('==', '>', '<', '<=', '>=')

    class ReturnValueTestSchema(CamelCaseSchema):
        comparator = fields.Str()
        value = fields.Str()

        @post_load
        def make(self, data, **kwargs):
            return ReturnValueTest(**data)

    def __init__(self, comparator: str, value: Union[int, str]):
        comparator, value = self.sanitize(comparator, value)
        self.comparator = comparator
        self.value = value

    def sanitize(self, comparator: str, value: str) -> Tuple[str, str]:
        if comparator not in self.COMPARATORS:
            raise ValueError(f'{comparator} is not a permitted comparator.')
        return comparator, value

    def eval(self, data) -> bool:
        # TODO: Sanitize input
        result = eval(f'{data}{self.comparator}{self.value}')
        return result


class ConditionLingo:
    # TODO: 'A Collection of re-encryption conditions evaluated as a compound boolean condition'

    def __init__(self, lingo: List[Union[ReencryptionCondition, Operator, Any]]):
        """
        The input list must be structured:
        condition
        operator
        condition
        ...
        """
        self._validate(lingo=lingo)
        self.lingo = lingo

    @staticmethod
    def _validate(lingo) -> None:
        if len(lingo) % 2 == 0:
            raise ValueError('conditions must be odd length, ever other element being an operator')
        for index, element in enumerate(lingo):
            if (not index % 2) and not (isinstance(element, ReencryptionCondition)):
                raise Exception(f'{index} element must be a condition; Got {type(element)}.')
            elif (index % 2) and (not isinstance(element, Operator)):
                raise Exception(f'{index} element must be an operator; Got {type(element)}.')

    def to_json(self) -> str:
        json_serialized_lingo = [l.to_dict() for l in self.lingo]
        data = json.dumps(json_serialized_lingo)
        return data

    @classmethod
    def from_json(cls, data: str) -> 'ConditionLingo':
        data = json.loads(data)
        lingo = [_deserialize_condition_lingo(l) for l in data]
        instance = cls(lingo=lingo)
        return instance

    def to_base64(self) -> bytes:
        data = base64.b64encode(self.to_json().encode())
        return data

    @classmethod
    def from_base64(cls, data: bytes) -> 'ConditionLingo':
        data = base64.b64decode(data).decode()
        instance = cls.from_json(data)
        return instance

    def __bytes__(self):
        data = self.to_base64()
        return data

    @classmethod
    def from_bytes(cls, data: bytes) -> 'ConditionLingo':
        instance = cls.from_base64(data)
        return instance

    def __eval(self, eval_string: str):
        # TODO: Additional protection and/or sanitation here
        result = eval(eval_string)
        return result

    def __process(self, *args, **kwargs):
        for task in self.lingo:
            if isinstance(task, ReencryptionCondition):
                condition = task
                result, value = condition.verify(*args, **kwargs)
                yield result
            elif isinstance(task, Operator):
                operator = task
                yield operator
            else:
                raise RuntimeError

    def eval(self, *args, **kwargs) -> bool:
        data = self.__process(*args, **kwargs)
        # [True, <Operator>, False] -> 'True or False'
        eval_string = ' '.join(str(e) for e in data)
        result = self.__eval(eval_string=eval_string)
        return result


OR = Operator('or')
AND = Operator('and')
