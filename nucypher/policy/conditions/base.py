import json
from abc import ABC, abstractmethod
from base64 import b64decode, b64encode
from typing import Any, List, Optional, Tuple

from marshmallow import Schema, ValidationError, fields

from nucypher.policy.conditions.exceptions import (
    InvalidCondition,
    InvalidConditionLingo,
)
from nucypher.policy.conditions.utils import CamelCaseSchema


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
    CONDITION_TYPE = NotImplemented

    class Schema(CamelCaseSchema):
        SKIP_VALUES = (None,)
        name = fields.Str(required=False)
        condition_type = NotImplemented

    def __init__(self, condition_type: str, name: Optional[str] = None):
        super().__init__()

        if condition_type != self.CONDITION_TYPE:
            raise InvalidCondition(
                f"{self.__class__.__name__} must be instantiated with the {self.CONDITION_TYPE} type."
            )
        self.condition_type = condition_type
        self.name = name

        self._validate()

    @abstractmethod
    def verify(self, *args, **kwargs) -> Tuple[bool, Any]:
        """Returns the boolean result of the evaluation and the returned value in a two-tuple."""
        raise NotImplementedError

    def _validate(self):
        # validate using marshmallow schema
        errors = self.Schema().validate(data=self.to_dict())
        if errors:
            raise InvalidCondition(f"Invalid {self.__class__.__name__}: {errors}")

    @classmethod
    def from_dict(cls, data) -> "AccessControlCondition":
        try:
            return super().from_dict(data)
        except ValidationError as e:
            raise InvalidConditionLingo(f"Invalid condition grammar: {e}") from e

    @classmethod
    def from_json(cls, data) -> "AccessControlCondition":
        try:
            return super().from_json(data)
        except ValidationError as e:
            raise InvalidConditionLingo(f"Invalid condition grammar: {e}") from e


class ExecutionCall(ABC):
    @abstractmethod
    def execute(self, *args, **kwargs) -> Any:
        raise NotImplementedError


class MultiConditionAccessControl(AccessControlCondition):
    MAX_NUM_CONDITIONS = 5
    MAX_MULTI_CONDITION_NESTED_LEVEL = 2

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def _validate(self):
        self._validate_multi_condition_nesting(conditions=self.conditions)

        super()._validate()

    @property
    @abstractmethod
    def conditions(self) -> List[AccessControlCondition]:
        raise NotImplementedError

    @classmethod
    def _validate_multi_condition_nesting(
        cls,
        conditions: List[AccessControlCondition],
        field_name: str,
        current_level: int = 1,
    ):
        if len(conditions) > cls.MAX_NUM_CONDITIONS:
            raise ValidationError(
                field_name=field_name,
                message=f"Maximum of {cls.MAX_NUM_CONDITIONS} conditions are allowed"
            )

        for condition in conditions:
            if not isinstance(condition, MultiConditionAccessControl):
                continue

            level = current_level + 1
            if level > cls.MAX_MULTI_CONDITION_NESTED_LEVEL:
                raise ValidationError(
                    field_name=field_name,
                    message=f"Only {cls.MAX_MULTI_CONDITION_NESTED_LEVEL} nested levels of multi-conditions are allowed"
                )
            cls._validate_multi_condition_nesting(
                conditions=condition.conditions,
                field_name=field_name,
                current_level=level,
            )
