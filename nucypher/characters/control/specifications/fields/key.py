from marshmallow import fields

class KeyField(fields.Field):

    def _serialize(self, value, attr, obj, **kwargs):

        return value

    def _deserialize(self, value, attr, data, **kwargs):
        return value

fields.Key = KeyField