from functools import wraps

from marshmallow import Schema, INCLUDE, EXCLUDE
from apispec.ext.marshmallow.field_converter import FieldConverterMixin
from nucypher.characters.control.specifications.exceptions import InvalidInputData
from nucypher.characters.control.specifications import fields

# we update https://github.com/marshmallow-code/apispec/blob/dev/src/apispec/ext/marshmallow/field_converter.py#L26
# with our own custom field types
DEFAULT_FIELD_MAPPING = {
    fields.Integer: ("integer", "int32"),
    fields.Number: ("number", None),
    fields.Float: ("number", "float"),
    fields.Decimal: ("number", None),
    fields.String: ("string", None),
    fields.Boolean: ("boolean", None),
    fields.UUID: ("string", "uuid"),
    fields.DateTime: ("string", "date-iso8601"),
    fields.Date: ("string", "date"),
    fields.Time: ("string", None),
    fields.Email: ("string", "email"),
    fields.URL: ("string", "url"),
    fields.Dict: ("object", None),
    fields.Field: (None, None),
    fields.Raw: (None, None),
    fields.List: ("array", None),
    # custom fields below
    fields.Key: ("string", "key"),
}

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





