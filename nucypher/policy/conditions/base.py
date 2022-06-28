import json
from abc import ABC, abstractmethod

from marshmallow import Schema, fields, post_load


def camelcase(s):
    parts = iter(s.split("_"))
    return next(parts) + "".join(i.title() for i in parts)


class CamelCaseSchema(Schema):
    """Schema that uses camel-case for its external representation
    and snake-case for its internal representation.
    """

    def on_bind_field(self, field_name, field_obj):
        field_obj.data_key = camelcase(field_obj.data_key or field_name)


class JSONSerializableCondition(ABC):

    class Schema(CamelCaseSchema):
        field = NotImplemented

    @classmethod
    def from_json(cls, data):
        data = json.loads(data)
        schema = cls.Schema()
        instance = schema.load(data)
        return instance

    def to_json(self) -> str:
        schema = self.Schema()
        data = schema.dumps(self)
        return data


class Operator(JSONSerializableCondition):

    class OperatorSchema(CamelCaseSchema):
        operator = fields.Str()

        @post_load
        def make(self, data, **kwargs):
            return Operator(**data)

    def __init__(self, operator: str):
        self.operator = operator


class ReencryptionCondition(JSONSerializableCondition, ABC):
    """Baseclass for reencryption preconditions relating to a policy."""

    ONCHAIN = NotImplemented
    NAME = NotImplemented

    @abstractmethod
    def verify(self, *args, **kwargs) -> bool:
        """returns True if reencryption is permitted by the payee (ursula) for the given reencryption request."""
        raise NotImplemented
