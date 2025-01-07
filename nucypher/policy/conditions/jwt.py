from typing import Any, Optional, Tuple

import jwt
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives.asymmetric import ec, rsa
from cryptography.hazmat.primitives.serialization import load_pem_public_key
from marshmallow import ValidationError, fields, post_load, validate, validates

from nucypher.policy.conditions.base import ExecutionCall
from nucypher.policy.conditions.context import (
    is_context_variable,
    resolve_any_context_variables,
)
from nucypher.policy.conditions.exceptions import JWTException
from nucypher.policy.conditions.lingo import (
    ConditionType,
    ExecutionCallAccessControlCondition,
    ReturnValueTest,
)
from nucypher.utilities.logging import Logger


class JWTVerificationCall(ExecutionCall):

    _valid_jwt_algorithms = (
        "ES256",
        "RS256",
    )  # https://datatracker.ietf.org/doc/html/rfc7518#section-3.1

    SECP_CURVE_FOR_ES256 = "secp256r1"

    class Schema(ExecutionCall.Schema):
        jwt_token = fields.Str(required=True)
        # TODO: See #3572 for a discussion about deprecating this in favour of the expected issuer
        public_key = fields.Str(
            required=True
        )  # required? maybe a valid PK certificate passed by requester?
        expected_issuer = fields.Str(required=False, allow_none=True)
        # TODO: StringOrURI as per the spec.

        @post_load
        def make(self, data, **kwargs):
            return JWTVerificationCall(**data)

        @validates("jwt_token")
        def validate_jwt_token(self, value):
            if not is_context_variable(value):
                raise ValidationError(
                    f"Invalid value for JWT token; expected a context variable, but got '{value}'"
                )

        @validates("public_key")
        def validate_public_key(self, value):
            try:
                public_key = load_pem_public_key(
                    value.encode(), backend=default_backend()
                )
                if isinstance(public_key, rsa.RSAPublicKey):
                    return value
                elif isinstance(public_key, ec.EllipticCurvePublicKey):
                    curve = public_key.curve
                    if curve.name != JWTVerificationCall.SECP_CURVE_FOR_ES256:
                        raise ValidationError(
                            f"Invalid EC public key curve: {curve.name}"
                        )
            except Exception as e:
                raise ValidationError(f"Invalid public key format: {str(e)}")

            return value

    def __init__(
        self,
        jwt_token: str,
        public_key: str,
        expected_issuer: Optional[str] = None,
    ):
        self.jwt_token = jwt_token
        self.public_key = public_key
        self.expected_issuer = expected_issuer

        self.logger = Logger(__name__)

        super().__init__()

    def execute(self, **context) -> Any:
        jwt_token = resolve_any_context_variables(self.jwt_token, **context)

        require = []
        if self.expected_issuer:
            require.append("iss")

        try:
            payload = jwt.decode(
                jwt=jwt_token,
                key=self.public_key,
                algorithms=self._valid_jwt_algorithms,
                options=dict(require=require),
                issuer=self.expected_issuer,
            )
        except jwt.exceptions.InvalidAlgorithmError:
            raise JWTException(f"valid algorithms: {self._valid_jwt_algorithms}")
        except jwt.exceptions.InvalidTokenError as e:
            raise JWTException(e)

        return payload


class JWTCondition(ExecutionCallAccessControlCondition):
    """
    A JWT condition can be satisfied by presenting a valid JWT token, which not only is
    required to be cryptographically verifiable, but also must fulfill certain additional
    restrictions defined in the condition.
    """

    EXECUTION_CALL_TYPE = JWTVerificationCall
    CONDITION_TYPE = ConditionType.JWT.value

    class Schema(
        ExecutionCallAccessControlCondition.Schema, JWTVerificationCall.Schema
    ):
        condition_type = fields.Str(
            validate=validate.Equal(ConditionType.JWT.value), required=True
        )

        @post_load
        def make(self, data, **kwargs):
            return JWTCondition(**data)

    def __init__(
        self,
        jwt_token: str,
        public_key: str,
        condition_type: str = ConditionType.JWT.value,
        name: Optional[str] = None,
        expected_issuer: Optional[str] = None,
    ):
        super().__init__(
            jwt_token=jwt_token,
            public_key=public_key,
            expected_issuer=expected_issuer,
            condition_type=condition_type,
            name=name,
            return_value_test=ReturnValueTest(
                comparator="==", value=True
            ),  # TODO: Workaround for now
        )

    @property
    def jwt_token(self):
        return self.execution_call.jwt_token

    @property
    def public_key(self):
        return self.execution_call.public_key

    @property
    def expected_issuer(self):
        return self.execution_call.expected_issuer

    def verify(self, **context) -> Tuple[bool, Any]:
        payload = self.execution_call.execute(**context)
        result = True
        return result, payload
