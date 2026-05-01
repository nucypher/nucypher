import json
from abc import ABC, abstractmethod
from base64 import b64decode, b64encode
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any, List, Optional, Tuple

from marshmallow import Schema, ValidationError, fields

from nucypher.policy.conditions.exceptions import (
    InvalidCondition,
    InvalidConditionLingo,
)
from nucypher.policy.conditions.utils import (
    CamelCaseSchema,
    extract_single_error_message_from_schema_errors,
)

_in_marshmallow_postload_construction: ContextVar[bool] = ContextVar(
    "_in_marshmallow_postload_construction",
    default=False,
)


@contextmanager
def marshmallow_postload_construction():
    token = _in_marshmallow_postload_construction.set(True)
    try:
        yield
    finally:
        _in_marshmallow_postload_construction.reset(token)


def constructed_from_marshmallow_postload() -> bool:
    return _in_marshmallow_postload_construction.get()


class _Serializable:
    class Schema(Schema):
        field = NotImplemented

    def to_json(self) -> str:
        schema = self.Schema()
        data = schema.dumps(self)
        return data

    @classmethod
    def from_json(cls, data) -> '_Serializable':
        data_dict = json.loads(data)
        return cls.from_dict(data_dict)

    def to_dict(self):
        schema = self.Schema()
        data = schema.dump(self)
        return data

    @classmethod
    def from_dict(cls, data) -> '_Serializable':
        schema = cls.Schema()
        with marshmallow_postload_construction():
            # set context variable to indicate that we're constructing from marshmallow's post_load
            instance = schema.load(data)
        return instance

    def __bytes__(self) -> bytes:
        json_payload = self.to_json().encode("utf-8")
        b64_json_payload = b64encode(json_payload)
        return b64_json_payload

    @classmethod
    def from_bytes(cls, data: bytes) -> "_Serializable":
        json_payload = b64decode(data).decode("utf-8")
        instance = cls.from_json(json_payload)
        return instance

    def _force_validate_with_schema(self):
        # perform actual validation since object instantiation is not being done by marshmallow's post_load
        errors = self.Schema().validate(data=self.to_dict())
        if errors:
            error_message = extract_single_error_message_from_schema_errors(errors)
            raise ValueError(f"Invalid {self.__class__.__name__}: {error_message}")

    def _validate(self, **kwargs):
        if not constructed_from_marshmallow_postload():
            self._force_validate_with_schema()


class Condition(_Serializable, ABC):
    CONDITION_TYPE = NotImplemented

    class Schema(CamelCaseSchema):
        name = fields.Str(required=False, allow_none=True)
        condition_type = NotImplemented

    def __init__(self, condition_type: str, name: Optional[str] = None):
        super().__init__()

        self.condition_type = condition_type
        self.name = name

        try:
            self._validate()
        except ValueError as e:
            raise InvalidCondition(f"{e}")

    def __repr__(self):
        return f"{self.__class__.__name__}"

    @abstractmethod
    def verify(self, *args, **kwargs) -> Tuple[bool, Any]:
        """Returns the boolean result of the evaluation and the returned value in a two-tuple."""
        raise NotImplementedError

    @classmethod
    def from_dict(cls, data) -> "Condition":
        try:
            return super().from_dict(data)
        except ValidationError as e:
            raise InvalidConditionLingo(f"Invalid condition grammar: {e}") from e

    @classmethod
    def from_json(cls, data) -> "Condition":
        try:
            return super().from_json(data)
        except ValidationError as e:
            raise InvalidConditionLingo(f"Invalid condition grammar: {e}") from e


class MultiCondition(Condition):
    MAX_NUM_CONDITIONS = 5
    MAX_MULTI_CONDITION_NESTED_LEVEL = 4

    @property
    @abstractmethod
    def conditions(self) -> List[Condition]:
        raise NotImplementedError

    @classmethod
    def _validate_multi_condition_nesting(
        cls,
        conditions: List[Condition],
        field_name: str,
        current_level: int = 1,
    ):
        if len(conditions) > cls.MAX_NUM_CONDITIONS:
            raise ValidationError(
                field_name=field_name,
                message=f"Maximum of {cls.MAX_NUM_CONDITIONS} conditions are allowed",
            )

        for condition in conditions:
            if not isinstance(condition, MultiCondition):
                continue

            level = current_level + 1
            if level > cls.MAX_MULTI_CONDITION_NESTED_LEVEL:
                raise ValidationError(
                    field_name=field_name,
                    message=f"Only {cls.MAX_MULTI_CONDITION_NESTED_LEVEL} nested levels of multi-conditions are allowed",
                )
            condition._validate_multi_condition_nesting(
                conditions=condition.conditions,
                field_name=field_name,
                current_level=level,
            )


class ExecutionCall(_Serializable, ABC):
    class InvalidExecutionCall(ValueError):
        pass

    class Schema(CamelCaseSchema):
        pass

    def __init__(self):
        # validate call using marshmallow schema before creating
        try:
            self._validate()
        except ValueError as e:
            raise self.InvalidExecutionCall(f"{e}")

    @abstractmethod
    def execute(self, *args, **kwargs) -> Any:
        raise NotImplementedError
