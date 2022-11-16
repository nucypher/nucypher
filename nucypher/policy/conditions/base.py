

import json
from abc import ABC, abstractmethod
from base64 import b64decode, b64encode
from typing import Any, Dict, Tuple

from marshmallow import Schema


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

    def to_dict(self) -> Dict[str, str]:
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


class ReencryptionCondition(_Serializable, ABC):

    class Schema(Schema):
        name = NotImplemented

    @abstractmethod
    def verify(self, *args, **kwargs) -> Tuple[bool, Any]:
        """Returns the boolean result of the evaluation and the returned value in a two-tuple."""
        return NotImplemented
