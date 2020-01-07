from base64 import b64decode, b64encode
from marshmallow import fields

class CleartextField(fields.Field):

    def _serialize(self, value, attr, data, **kwargs):
        return b64encode(value).decode()

fields.Cleartext = CleartextField