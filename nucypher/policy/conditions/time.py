import time
from marshmallow import fields, post_load
from typing import Tuple

from nucypher.policy.conditions._utils import CamelCaseSchema
from nucypher.policy.conditions.base import ReencryptionCondition
from nucypher.policy.conditions.lingo import ReturnValueTest


class TimeCondition(ReencryptionCondition):
    METHOD = 'timelock'

    class Schema(CamelCaseSchema):
        name = fields.Str()
        method = fields.Str(default='timelock')
        return_value_test = fields.Nested(ReturnValueTest.ReturnValueTestSchema())

        @post_load
        def make(self, data, **kwargs):
            return TimeCondition(**data)

    def __repr__(self) -> str:
        r = f'{self.__class__.__name__}(timestamp={self.return_value_test.value})'
        return r

    def __init__(self, return_value_test: ReturnValueTest, method: str = METHOD):
        if method != self.METHOD:
            raise Exception(f'{self.__class__.__name__} must be instantiated with the {self.METHOD} method.')
        self.return_value_test = return_value_test

    @property
    def method(self):
        return self.METHOD

    @property
    def timestamp(self):
        return self.return_value_test.value

    def verify(self, *args, **kwargs) -> Tuple[bool, float]:
        eval_time = time.time()
        return self.return_value_test.eval(data=eval_time), eval_time
