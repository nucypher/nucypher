from marshmallow import fields
from marshmallow.exceptions import ValidationError
from umbral.keys import UmbralPublicKey


class KeyField(fields.Field):

    def _serialize(self, value, attr, obj, **kwargs):
        return bytes(value).hex()

    def _deserialize(self, value, attr, data, **kwargs):
        if isinstance(value, bytes):
            return value
        try:
            return bytes.fromhex(value)
        except ValueError as e:
            raise ValidationError(e)

    def _validate(self, value):
        try:
            umbral_key = UmbralPublicKey.from_bytes(value)
            return True
        except Exception as e:
            return False

fields.Key = KeyField
