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
from typing import Optional, Set


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
    def connect_cli(cls, action, exclude: Optional[Set[str]] = None):
        """
        Provides click CLI options based on the defined schema for the action.

        "exclude" can be used to allow CLI to exclude a subset of click options from the schema from being defined,
        and allow the CLI to define them differently. For example, it can be used to exclude a required schema click
        option and allow the CLI to make it not required.
        """
        schema = getattr(cls, action)._schema

        def callable(func):
            c = func
            for f in [f for f in schema.load_fields.values() if f.click and (not exclude or f.name not in exclude)]:
                c = f.click(c)

            @functools.wraps(func)
            def wrapped(*args, **kwargs):
                return c(*args, **kwargs)

            return wrapped

        return callable
