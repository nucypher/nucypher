from marshmallow import fields
from umbral.keys import UmbralPublicKey

from nucypher.characters.control.specifications.exceptions import InvalidInputData, InvalidNativeDataTypes
from nucypher.characters.control.specifications.fields.base import BaseField


class Key(BaseField, fields.Field):

    def _serialize(self, value, attr, obj, **kwargs):
        return bytes(value).hex()

    def _deserialize(self, value, attr, data, **kwargs):
        if isinstance(value, bytes):
            return value
        try:
            return bytes.fromhex(value)
        except InvalidNativeDataTypes as e:
            raise InvalidInputData(f"Could not convert input for {self.name} to an Umbral Key: {e}")

    def _validate(self, value):
        try:
            UmbralPublicKey.from_bytes(value)
        except InvalidNativeDataTypes as e:
            raise InvalidInputData(f"Could not convert input for {self.name} to an Umbral Key: {e}")
