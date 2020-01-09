from base64 import b64decode, b64encode
from marshmallow import fields
from nucypher.characters.control.specifications.fields.base import BaseField
from nucypher.crypto.kits import UmbralMessageKit


class UmbralMessageKit(BaseField, fields.Field):

    def _serialize(self, value: UmbralMessageKit, attr, obj, **kwargs):
        return b64encode(value.to_bytes()).decode()

    def _deserialize(self, value, attr, data, **kwargs):
        if isinstance(value, bytes):
            return value
        return b64decode(value)

    def _validate(self, value):
        try:
            umbral_key = UmbralMessageKit.from_bytes(value)
            return True
        except Exception as e:
            return False
