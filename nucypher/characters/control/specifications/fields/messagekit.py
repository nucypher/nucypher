from base64 import b64decode, b64encode
from marshmallow import fields
from nucypher.characters.control.specifications.fields.base import BaseField
from nucypher.crypto.kits import UmbralMessageKit as UmbralMessageKitClass
from nucypher.characters.control.specifications.exceptions import InvalidInputData, InvalidNativeDataTypes


class UmbralMessageKit(BaseField, fields.Field):

    def _serialize(self, value: UmbralMessageKitClass, attr, obj, **kwargs):
        return b64encode(value.to_bytes()).decode()

    def _deserialize(self, value, attr, data, **kwargs):
        if isinstance(value, bytes):
            return value
        try:
            return b64decode(value)
        except InvalidNativeDataTypes as e:
            raise InvalidInputData(f"Could not parse {self.name}: {e}")

    def _validate(self, value):
        try:
            UmbralMessageKitClass.from_bytes(value)
        except InvalidNativeDataTypes as e:
            raise InvalidInputData(f"Could not parse {self.name}: {e}")
