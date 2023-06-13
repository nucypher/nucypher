import json
from abc import ABC, abstractmethod
from base64 import b64decode, b64encode
from typing import Any, Dict, Tuple

from marshmallow import Schema, ValidationError

from nucypher.policy.conditions.exceptions import (
    InvalidCondition,
    InvalidConditionLingo,
)


class _Serializable:
    class Schema(Schema):
        field = NotImplemented

    def to_json(self) -> str:
        schema = self.Schema()
        data = schema.dumps(self)
        return data

    @classmethod
    def from_json(cls, data) -> '_Serializable':
        data = json.loads(data)
        schema = cls.Schema()
        instance = schema.load(data)
        return instance

    def to_dict(self):
        schema = self.Schema()
        data = schema.dump(self)
        return data

    @classmethod
    def from_dict(cls, data) -> '_Serializable':
        schema = cls.Schema()
        instance = schema.load(data)
        return instance

    def __bytes__(self) -> bytes:
        json_payload = self.to_json().encode()
        b64_json_payload = b64encode(json_payload)
        return b64_json_payload

    @classmethod
    def from_bytes(cls, data: bytes) -> '_Serializable':
        json_payload = b64decode(data).decode()
        instance = cls.from_json(json_payload)
        return instance


class AccessControlCondition(_Serializable, ABC):

    class Schema(Schema):
        name = NotImplemented

    @abstractmethod
    def verify(self, *args, **kwargs) -> Tuple[bool, Any]:
        """Returns the boolean result of the evaluation and the returned value in a two-tuple."""
        return NotImplemented

    @classmethod
    def validate(cls, data: Dict) -> None:
        errors = cls.Schema().validate(data=data)
        if errors:
            raise InvalidCondition(f"Invalid {cls.__name__}: {errors}")

    @classmethod
    def from_dict(cls, data) -> "AccessControlCondition":
        try:
            return super().from_dict(data)
        except ValidationError as e:
            raise InvalidConditionLingo(f"Invalid condition grammar: {e}")

    @classmethod
    def from_json(cls, data) -> "AccessControlCondition":
        try:
            return super().from_json(data)
        except ValidationError as e:
            raise InvalidConditionLingo(f"Invalid condition grammar: {e}")
