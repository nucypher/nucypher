from enum import Enum
from typing import List, Union

from marshmallow.fields import String
from marshmallow.validate import OneOf


class AuthorizationType(Enum):
    BEARER = "Bearer"
    X_API_KEY = "X-API-Key"
    BASIC = "Basic"

    @classmethod
    def values(cls) -> List[str]:
        return [auth_type.value for auth_type in cls]

    def __str__(self):
        return self.value

    def header_name(self) -> str:
        if self in [self.BEARER, self.BASIC]:
            return "Authorization"
        else:
            return self.value

    def header_value(self, token: str) -> str:
        if self in [self.BEARER, self.BASIC]:
            return f"{self.value} {token}"
        else:
            return token


class AuthorizationTypeField(String):
    default_error_messages = {
        "invalidType": "Expression of type {value} is not valid for AuthorizationType",
        "invalid": "'{value}' is not a valid AuthorizationType",
    }

    def __init__(self, *args, **kwargs):
        super().__init__(validate=OneOf(AuthorizationType), *args, **kwargs)

    def _serialize(self, value, attr, obj, **kwargs) -> Union[str, None]:
        # If value is None, return None to allow for optional fields
        if value is None:
            return None

        if not isinstance(value, AuthorizationType):
            raise self.make_error("invalidType", value=type(value))

        return str(value)

    def _deserialize(self, value, attr, data, **kwargs):
        if not isinstance(value, str):
            raise self.make_error("invalidType", value=type(value))
        try:
            return AuthorizationType(value)
        except ValueError as e:
            raise self.make_error("invalid", value=value) from e
