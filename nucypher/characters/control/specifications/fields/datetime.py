from marshmallow import fields
import maya

class DateTimeField(fields.Field):

    def _serialize(self, value, attr, obj, **kwargs):
        return value.iso8601()

    def _deserialize(self, value, attr, data, **kwargs):
        return maya.MayaDT.from_iso8601(iso8601_string=value)

fields.DateTime = DateTimeField


