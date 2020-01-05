from marshmallow import fields
from base64 import b64decode, b64encode


class MessageKitField(fields.Field):

    def _serialize(self, value, attr, obj, **kwargs):
        breakpoint()
        return b64encode(bytes(value)).decode()

    def _deserialize(self, value, attr, data, **kwargs):
        if isinstance(value, bytes):
            return value
        return b64decode(value)

fields.MessageKit = MessageKitField