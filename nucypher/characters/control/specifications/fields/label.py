from marshmallow import fields

from nucypher.characters.control.specifications.fields.base import BaseField


class Label(BaseField, fields.Field):

    def _serialize(self, value, attr, obj, **kwargs):
        return value.decode('utf-8')

    def _deserialize(self, value, attr, data, **kwargs):
        if isinstance(value, bytes):
            return value
        return value.encode()
