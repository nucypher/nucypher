import base64
import hashlib
from typing import Any, Optional, Tuple

from ecdsa import BadSignatureError, VerifyingKey
from ecdsa.util import sigdecode_der
from marshmallow import ValidationError, fields, post_load, validate, validates

from nucypher.policy.conditions.base import AccessControlCondition, ExecutionCall
from nucypher.policy.conditions.context import (
    USER_ADDRESS_CONTEXT,
    is_context_variable,
    resolve_any_context_variables,
)
from nucypher.policy.conditions.exceptions import (
    InvalidCondition,
)
from nucypher.utilities.logging import Logger


class ECDSAVerificationCall(ExecutionCall):
    # Use SHA-256 for hashing
    _hash_func = hashlib.sha256

    class Schema(ExecutionCall.Schema):
        message = fields.Raw(required=True)
        signature = fields.Str(required=True)
        verifying_key = fields.Str(required=True)

        @post_load
        def make(self, data, **kwargs):
            return ECDSAVerificationCall(**data)

        @validates("message")
        def validate_message(self, value):
            if not is_context_variable(value) and not isinstance(value, (str, bytes)):
                raise ValidationError(
                    f"Invalid value for message; expected a context variable, string, or bytes but got '{value}'"
                )

        @validates("signature")
        def validate_signature(self, value):
            if not is_context_variable(value):
                # Try to decode it to ensure it's valid base64
                try:
                    base64.b64decode(value)
                except Exception as e:
                    raise ValidationError(
                        f"Invalid signature format, must be base64 encoded: {str(e)}"
                    )

        @validates("verifying_key")
        def validate_verifying_key(self, value):
            try:
                VerifyingKey.from_pem(value.encode())
            except Exception as e:
                raise ValidationError(f"Invalid verifying key format: {str(e)}")

    def __init__(
        self,
        message: Any,
        signature: str,
        verifying_key: str,
    ):
        self.message = message
        self.signature = signature
        self.verifying_key = verifying_key
        self.logger = Logger(__name__)
        super().__init__()

    def execute(self, **context) -> bool:
        try:
            # Special handling for USER_ADDRESS_CONTEXT if it's provided directly as bytes or string
            if self.message == USER_ADDRESS_CONTEXT and USER_ADDRESS_CONTEXT in context:
                message = context[USER_ADDRESS_CONTEXT]
                # Direct use of the message if it's already bytes or string
                if isinstance(message, (bytes, str)):
                    if isinstance(message, str):
                        message = message.encode("utf-8")
                else:
                    # Fallback to normal resolution for complex objects
                    message = resolve_any_context_variables(self.message, **context)
            else:
                # Normal resolution for other cases
                message = resolve_any_context_variables(self.message, **context)

            signature_b64 = resolve_any_context_variables(self.signature, **context)

            # Ensure message is bytes
            if isinstance(message, str):
                message = message.encode("utf-8")

            # Decode the b64 signature
            try:
                signature = base64.b64decode(signature_b64)
            except Exception as e:
                self.logger.error(f"Error decoding signature: {e}")
                return False

            # Load the verifying key
            try:
                verifying_key = VerifyingKey.from_pem(self.verifying_key.encode())
            except Exception as e:
                self.logger.error(f"Error loading verifying key: {e}")
                return False

            # Verify the signature
            return verifying_key.verify(
                signature=signature,
                data=message,
                hashfunc=self._hash_func,
                sigdecode=sigdecode_der,
            )
        except BadSignatureError:
            return False
        except Exception as e:
            self.logger.error(f"Error during signature verification: {e}")
            return False


class ECDSACondition(AccessControlCondition):
    """
    An ECDSA condition is satisfied when a provided signature can be verified
    against a message using the provided verifying key.

    The condition expects:
    - message: The message that was signed
    - signature: The DER-encoded signature as a base64 string
    - verifying_key: The PEM-encoded ECDSA verifying key
    """

    CONDITION_TYPE = "ecdsa"  # Add this to ConditionType enum

    class Schema(AccessControlCondition.Schema, ECDSAVerificationCall.Schema):
        condition_type = fields.Str(validate=validate.Equal("ecdsa"), required=True)

        @post_load
        def make(self, data, **kwargs):
            return ECDSACondition(**data)

    def __init__(
        self,
        message: Any,
        signature: str,
        verifying_key: str,
        condition_type: str = CONDITION_TYPE,
        name: Optional[str] = None,
    ):
        try:
            self.execution_call = ECDSAVerificationCall(
                message=message,
                signature=signature,
                verifying_key=verifying_key,
            )
        except ExecutionCall.InvalidExecutionCall as e:
            raise InvalidCondition(str(e)) from e

        super().__init__(condition_type=condition_type, name=name)

    @property
    def message(self):
        return self.execution_call.message

    @property
    def signature(self):
        return self.execution_call.signature

    @property
    def verifying_key(self):
        return self.execution_call.verifying_key

    def verify(self, **context) -> Tuple[bool, Any]:
        result = self.execution_call.execute(**context)
        return result, result
