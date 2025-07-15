import hashlib
from typing import Any, Optional, Tuple

from ecdsa import BadSignatureError, NIST192p, VerifyingKey
from ecdsa.curves import Curve, curves
from ecdsa.util import sigdecode_string
from marshmallow import (
    ValidationError,
    fields,
    post_load,
    validate,
    validates,
    validates_schema,
)

from nucypher.policy.conditions.base import Condition, ExecutionCall
from nucypher.policy.conditions.context import (
    USER_ADDRESS_CONTEXT,
    is_context_variable,
    resolve_any_context_variables,
)
from nucypher.policy.conditions.exceptions import (
    InvalidCondition,
)
from nucypher.utilities.logging import Logger

SUPPORTED_ECDSA_CONDITION_CURVES = {c.name: c for c in curves}
DEFAULT_ECDSA_CONDITION_CURVE = NIST192p


class ECDSAVerificationCall(ExecutionCall):
    # Use SHA-256 for hashing
    _hash_func = hashlib.sha256

    class Schema(ExecutionCall.Schema):
        message = fields.Raw(required=True)
        signature = fields.Str(required=True)
        verifying_key = fields.Str(required=True)
        curve = fields.Str(
            required=False,
            validate=validate.OneOf(list(SUPPORTED_ECDSA_CONDITION_CURVES)),
        )

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
                try:
                    bytes.fromhex(value)
                except Exception as e:
                    raise ValidationError(
                        f"Invalid signature format, must be hex encoded: {str(e)}"
                    )

        @validates_schema
        def validate_verifying_key(self, data, **kwargs):
            value = data.get("verifying_key")
            curve_name = data.get("curve")
            if curve_name:
                if curve_name not in SUPPORTED_ECDSA_CONDITION_CURVES:
                    raise ValidationError(
                        f"Unsupported curve: {curve_name}. Supported curves are: {SUPPORTED_ECDSA_CONDITION_CURVES.keys()}"
                    )
                curve = SUPPORTED_ECDSA_CONDITION_CURVES[curve_name]
            else:
                curve = DEFAULT_ECDSA_CONDITION_CURVE
            try:
                verifying_key_bytes = bytes.fromhex(value)
            except ValueError:
                raise ValidationError(
                    "Invalid verifying key format, must be hex encoded"
                )
            try:
                VerifyingKey.from_string(
                    verifying_key_bytes,
                    curve=curve,
                )
            except Exception as e:
                raise ValidationError(
                    f"Invalid verifying key for curve {curve_name}: {str(e)}"
                )

    def __init__(self, message: Any, signature: str, verifying_key: str, curve: Curve):
        self.message = message
        self.signature = signature
        self.verifying_key = verifying_key
        self.curve = curve
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

            # Special handling for context variables - treat as hex-encoded bytes for ECDSA
            if is_context_variable(self.message):
                message_value = resolve_any_context_variables(self.message, **context)
                if isinstance(message_value, str):
                    try:
                        # Try to decode as hex first
                        message = bytes.fromhex(message_value)
                    except ValueError:
                        # If hex decoding fails, treat as regular string
                        message = message_value.encode("utf-8")
                else:
                    message = message_value
            elif isinstance(message, str):
                # Ensure message is bytes for non-context variables
                message = message.encode("utf-8")

            signature_hex = resolve_any_context_variables(self.signature, **context)

            # Decode the hex signature
            try:
                signature = bytes.fromhex(signature_hex)
            except Exception as e:
                self.logger.error(f"Error decoding signature: {e}")
                return False

            # Load the verifying key
            try:
                verifying_key = VerifyingKey.from_string(
                    string=bytes.fromhex(self.verifying_key),
                    curve=self.curve,
                )
            except Exception as e:
                self.logger.error(f"Error loading verifying key: {e}")
                return False

            # Verify the signature
            return verifying_key.verify(
                signature=signature,
                data=message,
                hashfunc=self._hash_func,
                sigdecode=sigdecode_string,
            )
        except BadSignatureError:
            return False
        except Exception as e:
            self.logger.error(f"Error during signature verification: {e}")
            return False


class ECDSACondition(Condition):
    """
    An ECDSA condition is satisfied when a provided signature can be verified
    against a message using the provided verifying key.

    The condition expects:
    - message: The message that was signed
    - signature: The DER-encoded signature as a base64 string
    - verifying_key: The PEM-encoded ECDSA verifying key
    """

    CONDITION_TYPE = "ecdsa"  # Add this to ConditionType enum

    class Schema(Condition.Schema, ECDSAVerificationCall.Schema):
        condition_type = fields.Str(validate=validate.Equal("ecdsa"), required=True)

        @post_load
        def make(self, data, **kwargs):
            return ECDSACondition(**data)

    def __init__(
        self,
        message: Any,
        signature: str,
        verifying_key: str,
        curve: Optional[str] = DEFAULT_ECDSA_CONDITION_CURVE.name,
        condition_type: str = CONDITION_TYPE,
        name: Optional[str] = None,
    ):
        if curve not in SUPPORTED_ECDSA_CONDITION_CURVES:
            raise InvalidCondition(
                f"Unsupported curve: {curve}. Supported curves are: {list(SUPPORTED_ECDSA_CONDITION_CURVES.keys())}"
            )

        try:
            self.execution_call = ECDSAVerificationCall(
                message=message,
                signature=signature,
                verifying_key=verifying_key,
                curve=SUPPORTED_ECDSA_CONDITION_CURVES[curve],
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

    @property
    def curve(self):
        return self.execution_call.curve

    def verify(self, **context) -> Tuple[bool, Any]:
        result = self.execution_call.execute(**context)
        return result, result
