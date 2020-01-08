from functools import wraps

from marshmallow import Schema, INCLUDE, EXCLUDE
from nucypher.characters.control.specifications.exceptions import InvalidInputField


def nucypher_command(func, *args, **kwargs):

    @wraps(func)
    def wrapped():
        result = func(*args, **kwargs)
        return result
    return wrapped


class BaseSchema(Schema):

    class Meta:

        unknown = INCLUDE   # pass through any data that isn't defined as a field

    def handle_error(self, error, data, many, **kwargs):
        raise InvalidInputField(error)

    def make_click_commands(self):
        for field in self.load_fields:
            pass
