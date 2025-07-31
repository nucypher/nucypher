import pytest
from marshmallow import ValidationError

from nucypher.policy.conditions.json.auth import (
    AuthorizationType,
    AuthorizationTypeField,
)


@pytest.fixture
def token():
    return "abcd-1234"


def test_bearer_auth_type(token):
    auth_type = AuthorizationType.BEARER
    assert str(auth_type) == "Bearer"
    assert auth_type.header_name() == "Authorization"
    assert auth_type.header_value(token) == f"Bearer {token}"


def test_basic_auth_type(token):
    auth_type = AuthorizationType.BASIC
    assert str(auth_type) == "Basic"
    assert auth_type.header_name() == "Authorization"
    assert auth_type.header_value(token) == f"Basic {token}"


def test_x_api_key_auth_type(token):
    auth_type = AuthorizationType.X_API_KEY
    assert str(auth_type) == "X-API-Key"
    assert auth_type.header_name() == "X-API-Key"
    assert auth_type.header_value(token) == token


@pytest.mark.parametrize("auth_type_str", AuthorizationType.values())
def test_auth_type_field(auth_type_str):
    auth_type = AuthorizationType(auth_type_str)

    auth_type_field = AuthorizationTypeField()

    serialized = auth_type_field._serialize(value=auth_type, attr=None, obj=None)
    assert serialized == auth_type_str

    deserialized = auth_type_field.deserialize(value=serialized)
    assert deserialized == auth_type


def test_auth_type_field_invalid_auth_type():
    auth_type_field = AuthorizationTypeField()

    with pytest.raises(ValidationError, match="is not a valid AuthorizationType"):
        auth_type_field.deserialize(value="invalid_auth_type")

    with pytest.raises(
        ValidationError, match="type <class 'int'> is not valid for AuthorizationType"
    ):
        auth_type_field.deserialize(value=1234)

    with pytest.raises(ValidationError, match="is not valid for AuthorizationType"):
        auth_type_field._serialize(value="invalid_auth_type", attr=None, obj=None)


# old conditions wouldn't have this field so it would be None
def test_auth_type_field_none_value():
    auth_type_field = AuthorizationTypeField(allow_none=True)

    # Test serialization of None
    serialized = auth_type_field._serialize(value=None, attr=None, obj=None)
    assert serialized is None

    # Test deserialization of None
    deserialized = auth_type_field.deserialize(value=None)
    assert deserialized is None
