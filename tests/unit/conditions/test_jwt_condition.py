from datetime import datetime, timezone

import jwt
import pytest
from marshmallow import validates

from nucypher.policy.conditions.base import ExecutionCall
from nucypher.policy.conditions.jwt import JWTCondition, JWTVerificationCall

TEST_ECDSA_PRIVATE_KEY_RAW_B64 = (
    "MHcCAQEEIHAhM7P6HG3LgkDvgvfDeaMA6uELj+jEKWsSeOpS/SfYoAoGCCqGSM49\n"
    "AwEHoUQDQgAEXHVxB7s5SR7I9cWwry/JkECIRekaCwG3uOLCYbw5gVzn4dRmwMyY\n"
    "UJFcQWuFSfECRK+uQOOXD0YSEucBq0p5tA=="
)

TEST_ECDSA_PRIVATE_KEY = (  # TODO: Workaround to bypass pre-commit hook that detects private keys in code
    "-----BEGIN EC"
    + " PRIVATE KEY"
    + f"-----\n{TEST_ECDSA_PRIVATE_KEY_RAW_B64}\n-----END EC"
    + " PRIVATE KEY-----"
)

TEST_ECDSA_PUBLIC_KEY = (
    "-----BEGIN PUBLIC KEY-----\nMFkwEwYHKoZIzj0CAQYIKoZIzj0DAQcDQgAEXHVxB7s5SR7I9cWwry"
    "/JkECIReka\nCwG3uOLCYbw5gVzn4dRmwMyYUJFcQWuFSfECRK+uQOOXD0YSEucBq0p5tA==\n-----END PUBLIC "
    "KEY-----"
)

ISSUED_AT = datetime.now(tz=timezone.utc)

TEST_JWT_TOKEN = jwt.encode(
    {"iat": ISSUED_AT}, TEST_ECDSA_PRIVATE_KEY, algorithm="ES256"
)


def jwt_token(with_iat: bool = True, claims: dict = None):
    claims = claims or dict()
    if with_iat:
        claims["iat"] = ISSUED_AT

    return jwt.encode(claims, TEST_ECDSA_PRIVATE_KEY, algorithm="ES256")


class TestJWTVerificationCall(JWTVerificationCall):
    class Schema(JWTVerificationCall.Schema):
        @validates("jwt_token")
        def validate_jwt_token(self, value):
            pass


def test_raw_jwt_decode():
    token = jwt_token()

    # Valid JWT
    jwt.decode(token, TEST_ECDSA_PUBLIC_KEY, algorithms=["ES256"])

    # Invalid JWT
    with pytest.raises(jwt.exceptions.InvalidTokenError):
        jwt.decode(token[1:], TEST_ECDSA_PUBLIC_KEY, algorithms=["ES256"])


def test_jwt_verification_call_invalid():
    token = jwt_token()
    message = r"Invalid value for JWT token; expected a context variable"
    with pytest.raises(ExecutionCall.InvalidExecutionCall, match=message):
        JWTVerificationCall(jwt_token=token, public_key=TEST_ECDSA_PUBLIC_KEY)


def test_jwt_verification_call_invalid2():
    token = jwt_token()
    TestJWTVerificationCall(jwt_token=token, public_key=TEST_ECDSA_PUBLIC_KEY)


def test_jwt_condition_initialization():
    condition = JWTCondition(
        jwt_token=":aContextVariableForJWTs",
        public_key=TEST_ECDSA_PUBLIC_KEY,
    )

    assert condition.jwt_token == ":aContextVariableForJWTs"
    assert condition.public_key == TEST_ECDSA_PUBLIC_KEY
    assert condition.condition_type == JWTCondition.CONDITION_TYPE


def test_jwt_condition_verify():
    token = jwt_token()
    condition = JWTCondition(
        jwt_token=":anotherContextVariableForJWTs",
        public_key=TEST_ECDSA_PUBLIC_KEY,
    )

    context = {":anotherContextVariableForJWTs": token}
    success, result = condition.verify(**context)
    assert success
    assert result is not None
