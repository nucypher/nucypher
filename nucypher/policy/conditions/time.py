"""
 This file is part of nucypher.

 nucypher is free software: you can redistribute it and/or modify
 it under the terms of the GNU Affero General Public License as published by
 the Free Software Foundation, either version 3 of the License, or
 (at your option) any later version.

 nucypher is distributed in the hope that it will be useful,
 but WITHOUT ANY WARRANTY; without even the implied warranty of
 MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
 GNU Affero General Public License for more details.

 You should have received a copy of the GNU Affero General Public License
 along with nucypher.  If not, see <https://www.gnu.org/licenses/>.
"""

import time
from typing import Tuple

from marshmallow import fields, post_load

from nucypher.policy.conditions._utils import CamelCaseSchema
from nucypher.policy.conditions.base import ReencryptionCondition
from nucypher.policy.conditions.exceptions import InvalidCondition
from nucypher.policy.conditions.lingo import ReturnValueTest


class TimeCondition(ReencryptionCondition):
    METHOD = 'timelock'

    class Schema(CamelCaseSchema):
        name = fields.Str()
        method = fields.Str(dump_default="timelock")
        return_value_test = fields.Nested(ReturnValueTest.ReturnValueTestSchema())

        @post_load
        def make(self, data, **kwargs):
            return TimeCondition(**data)

    def __repr__(self) -> str:
        r = f'{self.__class__.__name__}(timestamp={self.return_value_test.value})'
        return r

    def __init__(self, return_value_test: ReturnValueTest, method: str = METHOD):
        if method != self.METHOD:
            raise InvalidCondition(
                f"{self.__class__.__name__} must be instantiated with the {self.METHOD} method."
            )
        self.return_value_test = return_value_test

    @property
    def method(self):
        return self.METHOD

    @property
    def timestamp(self):
        return self.return_value_test.value

    def verify(self, *args, **kwargs) -> Tuple[bool, float]:
        eval_time = time.time()   # system  clock
        return self.return_value_test.eval(data=eval_time), eval_time
