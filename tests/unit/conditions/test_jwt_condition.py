import calendar
import re
from datetime import datetime, timezone

import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec
from marshmallow import validates

from nucypher.policy.conditions.base import ExecutionCall
from nucypher.policy.conditions.exceptions import InvalidCondition, JWTException
from nucypher.policy.conditions.jwt import JWTCondition, JWTVerificationCall


def generate_pem_keypair(elliptic_curve):
    # Generate an EC private key
    private_key = ec.generate_private_key(elliptic_curve)

    # Get the corresponding public key
    public_key = private_key.public_key()

    # Serialize the private key to PEM format
    pem_private_key = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.TraditionalOpenSSL,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode("utf-8")

    # Serialize the public key to PEM format
    pem_public_key = public_key.public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode("utf-8")

    return pem_public_key, pem_private_key


TEST_ECDSA_PUBLIC_KEY, TEST_ECDSA_PRIVATE_KEY = generate_pem_keypair(ec.SECP256R1())
ISSUED_AT = calendar.timegm(datetime.now(tz=timezone.utc).utctimetuple())
TEST_JWT_TOKEN = jwt.encode(
    {"iat": ISSUED_AT}, TEST_ECDSA_PRIVATE_KEY, algorithm="ES256"
)


def jwt_token(
    with_iat: bool = True, claims: dict = None, expiration_offset: int = None
):
    claims = claims or dict()
    if with_iat:
        claims["iat"] = ISSUED_AT
    if expiration_offset is not None:
        claims["exp"] = ISSUED_AT + expiration_offset

    return jwt.encode(claims, TEST_ECDSA_PRIVATE_KEY, algorithm="ES256")


class MockJWTVerificationCall(JWTVerificationCall):
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
        JWTVerificationCall(
            jwt_token=token, algorithm="ES256", public_key=TEST_ECDSA_PUBLIC_KEY
        )


def test_jwt_verification_call_valid():
    token = jwt_token()
    call = MockJWTVerificationCall(
        jwt_token=token, algorithm="ES256", public_key=TEST_ECDSA_PUBLIC_KEY
    )
    assert call.execute()


def test_jwt_condition_missing_jwt_token():
    with pytest.raises(
        InvalidCondition, match="'jwt_token' field - Field may not be null."
    ):
        _ = JWTCondition(
            jwt_token=None, algorithm="ES256", public_key=TEST_ECDSA_PUBLIC_KEY
        )


def test_jwt_condition_missing_algorithm():
    with pytest.raises(
        InvalidCondition, match="'algorithm' field - Field may not be null."
    ):
        _ = JWTCondition(
            jwt_token=":aContextVariableForJWTs",
            algorithm=None,
            public_key=TEST_ECDSA_PUBLIC_KEY,
        )


def test_jwt_condition_missing_public_key():
    with pytest.raises(
        InvalidCondition, match="'public_key' field - Field may not be null."
    ):
        _ = JWTCondition(
            jwt_token=":ok_ok_this_is_a_variable_for_a_jwt",
            algorithm="ES256",
            public_key=None,
        )


def test_jwt_condition_invalid_public_key():
    with pytest.raises(
        InvalidCondition,
        match="'public_key' field - Invalid public key format: Unable to load PEM",
    ):
        _ = JWTCondition(
            jwt_token=":ok_ok_this_is_a_variable_for_a_jwt",
            algorithm="ES256",
            public_key="-----BEGIN PUBLIC KEY----- haha, gotcha! 👌 -----END PUBLIC KEY-----",
        )


def test_jwt_condition_but_unsupported_algorithm():
    pem_secp521_public_key, _ = generate_pem_keypair(ec.SECP521R1())

    with pytest.raises(
        InvalidCondition,
        match=re.escape(
            "'algorithm' field - Invalid JWT algorithm; expected one of ('ES256', 'RS256'), but got 'ES512'"
        ),
    ):
        _ = JWTCondition(
            jwt_token=":ok_ok_this_is_a_variable_for_a_jwt",
            algorithm="ES512",
            public_key=pem_secp521_public_key,
        )


def test_jwt_condition_initialization():
    condition = JWTCondition(
        jwt_token=":aContextVariableForJWTs",
        algorithm="ES256",
        public_key=TEST_ECDSA_PUBLIC_KEY,
    )

    assert condition.jwt_token == ":aContextVariableForJWTs"
    assert condition.public_key == TEST_ECDSA_PUBLIC_KEY
    assert condition.condition_type == JWTCondition.CONDITION_TYPE


def test_jwt_condition_verify():
    token = jwt_token(with_iat=False)
    condition = JWTCondition(
        jwt_token=":anotherContextVariableForJWTs",
        algorithm="ES256",
        public_key=TEST_ECDSA_PUBLIC_KEY,
    )

    context = {":anotherContextVariableForJWTs": token}
    success, payload = condition.verify(**context)
    assert success
    assert payload == {}


def test_jwt_condition_verify_of_invalid_jwt():
    condition = JWTCondition(
        jwt_token=":anotherContextVariableForJWTs",
        algorithm="ES256",
        public_key=TEST_ECDSA_PUBLIC_KEY,
    )

    context = {":anotherContextVariableForJWTs": "obviously.invalid.token"}
    with pytest.raises(JWTException):
        _ = condition.verify(**context)


def test_jwt_condition_verify_of_jwt_with_custom_claims():
    token = jwt_token(with_iat=False, claims={"foo": "bar"})
    condition = JWTCondition(
        jwt_token=":anotherContextVariableForJWTs",
        algorithm="ES256",
        public_key=TEST_ECDSA_PUBLIC_KEY,
    )

    context = {":anotherContextVariableForJWTs": token}
    success, payload = condition.verify(**context)
    assert success
    assert payload == {"foo": "bar"}


def test_jwt_condition_verify_with_correct_issuer():
    token = jwt_token(with_iat=False, claims={"iss": "Isabel"})
    condition = JWTCondition(
        jwt_token=":anotherContextVariableForJWTs",
        algorithm="ES256",
        public_key=TEST_ECDSA_PUBLIC_KEY,
        expected_issuer="Isabel",
    )

    context = {":anotherContextVariableForJWTs": token}
    success, payload = condition.verify(**context)
    assert success
    assert payload == {"iss": "Isabel"}


def test_jwt_condition_verify_with_invalid_issuer():
    token = jwt_token(with_iat=False, claims={"iss": "Isabel"})
    condition = JWTCondition(
        jwt_token=":anotherContextVariableForJWTs",
        algorithm="ES256",
        public_key=TEST_ECDSA_PUBLIC_KEY,
        expected_issuer="Isobel",
    )

    context = {":anotherContextVariableForJWTs": token}
    with pytest.raises(JWTException, match="Invalid issuer"):
        _ = condition.verify(**context)


def test_jwt_condition_verify_expired_token():
    # Create a token that expired 100 seconds
    expired_token = jwt_token(with_iat=True, expiration_offset=-100)

    condition = JWTCondition(
        jwt_token=":contextVar",
        algorithm="ES256",
        public_key=TEST_ECDSA_PUBLIC_KEY,
    )

    context = {":contextVar": expired_token}
    with pytest.raises(JWTException, match="Signature has expired"):
        _ = condition.verify(**context)


def test_jwt_condition_verify_valid_token_with_expiration():
    # Create a token that will expire in 999 seconds
    expired_token = jwt_token(with_iat=False, expiration_offset=999)

    condition = JWTCondition(
        jwt_token=":contextVar",
        algorithm="ES256",
        public_key=TEST_ECDSA_PUBLIC_KEY,
    )

    context = {":contextVar": expired_token}
    success, payload = condition.verify(**context)
    assert success
    assert payload == {"exp": ISSUED_AT + 999}
