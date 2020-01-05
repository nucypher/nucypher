from marshmallow import fields

class LabelField(fields.Field):

    def _serialize(self, value, attr, obj, **kwargs):
        return value.decode('utf-8')

    def _deserialize(self, value, attr, data, **kwargs):
        if isinstance(value, bytes):
            return value
        return value.encode()

    def _validate(self, value):
        return True

fields.Label = LabelField