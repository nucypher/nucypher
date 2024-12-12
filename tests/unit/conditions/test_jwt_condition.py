import jwt
import pytest
from marshmallow import validates

from nucypher.policy.conditions.base import ExecutionCall
from nucypher.policy.conditions.jwt import JWTCondition, JWTVerificationCall

TEST_ECDSA_PUBLIC_KEY = (
    "-----BEGIN PUBLIC KEY-----\nMFkwEwYHKoZIzj0CAQYIKoZIzj0DAQcDQgAEXHVxB7s5SR7I9cWwry"
    "/JkECIReka\nCwG3uOLCYbw5gVzn4dRmwMyYUJFcQWuFSfECRK+uQOOXD0YSEucBq0p5tA==\n-----END PUBLIC "
    "KEY-----\n "
)
TEST_JWT_TOKEN = (
    "eyJhbGciOiJFUzI1NiIsInR5cCI6IkpXVCJ9"
    ".eyJpYXQiOjE3MzM0MjQ3MTd9"
    ".uc2Av6f4yibXRLtmCmvhbRiNfYTrkHPS3vAGHaamX1CQ4mQR8iGyE8X3TvseCclkgsbKBBKZG8nQXhA5hsXLRg"
)


class TestJWTVerificationCall(JWTVerificationCall):
    class Schema(JWTVerificationCall.Schema):
        @validates("jwt_token")
        def validate_jwt_token(self, value):
            pass


def test_raw_jwt_decode():
    # Valid JWT
    jwt.decode(TEST_JWT_TOKEN, TEST_ECDSA_PUBLIC_KEY, algorithms=["ES256"])

    # Invalid JWT
    with pytest.raises(jwt.exceptions.InvalidTokenError):
        jwt.decode(TEST_JWT_TOKEN[1:], TEST_ECDSA_PUBLIC_KEY, algorithms=["ES256"])


def test_jwt_verification_call_invalid():
    message = r"Invalid value for JWT token; expected a context variable"
    with pytest.raises(ExecutionCall.InvalidExecutionCall, match=message):
        JWTVerificationCall(jwt_token=TEST_JWT_TOKEN, public_key=TEST_ECDSA_PUBLIC_KEY)


def test_jwt_verification_call_invalid2():
    TestJWTVerificationCall(jwt_token=TEST_JWT_TOKEN, public_key=TEST_ECDSA_PUBLIC_KEY)


def test_jwt_condition_initialization():
    condition = JWTCondition(
        jwt_token=":aContextVariableForJWTs",
        public_key=TEST_ECDSA_PUBLIC_KEY,
    )

    assert condition.jwt_token == ":aContextVariableForJWTs"
    assert condition.public_key == TEST_ECDSA_PUBLIC_KEY
    assert condition.condition_type == JWTCondition.CONDITION_TYPE


def test_jwt_condition_verify():
    condition = JWTCondition(
        jwt_token=":anotherContextVariableForJWTs",
        public_key=TEST_ECDSA_PUBLIC_KEY,
    )

    context = {":anotherContextVariableForJWTs": TEST_JWT_TOKEN}
    success, result = condition.verify(**context)
    assert success
    assert result is not None
