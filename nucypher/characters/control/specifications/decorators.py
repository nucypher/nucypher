from functools import wraps
from importlib import import_module
import click


def specify_options(spec, action):
    module = import_module(f"nucypher.characters.control.specifications.{spec}")
    schema = getattr(module, action)

    def callable(func):
        c = func
        for k, f in schema().load_fields.items():
            c = click.option(*f.click.args, **f.click.kwargs)(c)

        @wraps(func)
        def wrapped(*args, **kwargs):
            return c(*args, **kwargs)
        return wrapped

    return callable
