from marshmallow import fields
from base64 import b64decode, b64encode
from nucypher.characters.control.specifications.fields.base import BaseField
from nucypher.characters.control.specifications.exceptions import InvalidInputData, InvalidNativeDataTypes


class TreasureMap(BaseField, fields.Field):

    def _serialize(self, value, attr, obj, **kwargs):
        return b64encode(bytes(value)).decode()

    def _deserialize(self, value, attr, data, **kwargs):
        try:
            return b64decode(value)
        except InvalidNativeDataTypes as e:
            raise InvalidInputData(f"Could not parse {self.name}: {e}")

    def _validate(self, value):
        from nucypher.policy.collections import TreasureMap
        try:
            TreasureMap.from_bytes(value)
            return True
        except InvalidNativeDataTypes as e:
            raise InvalidInputData(f"Could not parse {self.name}: {e}")


