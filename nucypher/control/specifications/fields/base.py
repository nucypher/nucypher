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

import click
from marshmallow import fields

from nucypher.control.specifications.exceptions import InvalidInputData


class BaseField:

    click_type = click.STRING

    def __init__(self, *args, **kwargs):
        self.click = kwargs.pop('click', None)
        super().__init__(*args, **kwargs)


#
# Very common, simple field types to build on.
#

class String(BaseField, fields.String):
    pass


class List(BaseField, fields.List):
    pass


class Integer(BaseField, fields.Integer):
    click_type = click.INT


class PositiveInteger(Integer):
    def _validate(self, value):
        if not value > 0:
            raise InvalidInputData(f"{self.name} must be a positive integer.")


#
# CLI utility
#

class click:
    def __init__(self, *args, **kwargs):
        self.args = args
        self.kwargs = kwargs
