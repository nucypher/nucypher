from base64 import b64decode, b64encode
from marshmallow import fields
from nucypher.characters.control.specifications.fields.base import BaseField

class Cleartext(BaseField, fields.String):

    def _serialize(self, value, attr, data, **kwargs):
        return value.decode()

    def _deserialize(self, value, attr, data, **kwargs):
        return b64encode(bytes(value, encoding='utf-8')).decode()
