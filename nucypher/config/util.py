

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
