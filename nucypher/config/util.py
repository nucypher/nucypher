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

from pathlib import Path
from typing import Optional, get_type_hints


def cast_paths_from(cls, payload):
    """
    A serialization helper.
    Iterates over constructor arguments of `cls` and `cls` parents. Finds arguments
    of type `pathlib.Path` or `Optional[pathlib.Path]`. Based on this, it casts
    corresponding values in `payload` from `str` to `pathlib.Path` or None.
    """
    constructor_args = get_type_hints(cls.__init__)
    for ancestor in cls.__mro__:
        constructor_args.update(get_type_hints(ancestor.__init__))
    paths_only = [
        arg for (arg, type_) in constructor_args.items()
        if type_ == Path or type_ == Optional[Path]
    ]
    for key in paths_only:
        if key in payload:
            payload[key] = Path(payload[key]) if payload[key] else None
    return payload
