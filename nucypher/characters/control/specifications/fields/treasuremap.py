from marshmallow import fields
from base64 import b64decode, b64encode

class TreasureMapField(fields.Field):

    def _serialize(self, value, attr, obj, **kwargs):
        return b64encode(bytes(value)).decode()

    def _deserialize(self, value, attr, data, **kwargs):
        return b64decode(value)

fields.TreasureMap = TreasureMapField