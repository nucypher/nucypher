from marshmallow import Schema, INCLUDE, EXCLUDE
from .exceptions import InvalidInputField

class BaseSchema(Schema):

    class Meta:

        unknown = INCLUDE # pass through any data that isn't defined as a field

    def handle_error(self, error, data, many, **kwargs):
        raise InvalidInputField(error)