from functools import wraps

from marshmallow import Schema, INCLUDE, EXCLUDE
from apispec.ext.marshmallow.field_converter import FieldConverterMixin
from nucypher.characters.control.specifications.exceptions import InvalidInputData

from nucypher.characters.control.specifications.constants import DEFAULT_FIELD_MAPPING

class BaseSchema(Schema, FieldConverterMixin):

    field_mapping = DEFAULT_FIELD_MAPPING

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.attribute_functions = [
            self.field2type_and_format,
            self.field2default,
            self.field2choices,
            self.field2nullable,
            self.field2range,
            self.field2length,
            self.field2pattern,
            self.metadata2properties,
            self.nested2properties,
            self.list2properties,
            self.dict2properties,
        ]

    class Meta:

        unknown = INCLUDE   # pass through any data that isn't defined as a field

    def handle_error(self, error, data, many, **kwargs):
        raise InvalidInputData(error)

    def as_options_dict(self):
        return {
            "type": "object",
            "properties": {
                name: self.field2property(field)
                for name, field in self.load_fields.items()
            }
        }





