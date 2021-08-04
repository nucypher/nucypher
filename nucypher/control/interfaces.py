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


import functools


def attach_schema(schema):
    def callable(func):
        func._schema = schema()

        @functools.wraps(func)
        def wrapped(*args, **kwargs):
            return func(*args, **kwargs)

        return wrapped

    return callable


class ControlInterface:

    def __init__(self, implementer=None, *args, **kwargs):
        self.implementer = implementer
        super().__init__(*args, **kwargs)

    @classmethod
    def connect_cli(cls, action):
        schema = getattr(cls, action)._schema

        def callable(func):
            c = func
            for f in [f for f in schema.load_fields.values() if f.click]:
                c = f.click(c)

            @functools.wraps(func)
            def wrapped(*args, **kwargs):
                return c(*args, **kwargs)

            return wrapped

        return callable
