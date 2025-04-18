import base64

import pytest
from ecdsa import SECP256k1, SigningKey
from ecdsa.util import sigencode_der
from marshmallow import validates

from nucypher.policy.conditions.ecdsa import ECDSACondition, ECDSAVerificationCall
from nucypher.policy.conditions.exceptions import (
    InvalidCondition,
)

# Generate test keys for ECDSA signing/verification
TEST_SIGNING_KEY = SigningKey.generate(curve=SECP256k1)
TEST_VERIFYING_KEY = TEST_SIGNING_KEY.verifying_key

# Get the PEM encoded verifying key
TEST_VERIFYING_KEY_PEM = TEST_VERIFYING_KEY.to_pem().decode("utf-8")

# Test message and signature
TEST_MESSAGE = b"This is a test message for ECDSA verification"
TEST_SIGNATURE = TEST_SIGNING_KEY.sign(
    TEST_MESSAGE, hashfunc=ECDSAVerificationCall._hash_func, sigencode=sigencode_der
)
TEST_SIGNATURE_B64 = base64.b64encode(TEST_SIGNATURE).decode("utf-8")


class TestECDSAVerificationCall(ECDSAVerificationCall):
    class Schema(ECDSAVerificationCall.Schema):
        @validates("message")
        def validate_message(self, value):
            pass

        @validates("signature")
        def validate_signature(self, value):
            pass


def test_ecdsa_verification_call_valid():
    call = TestECDSAVerificationCall(
        message=TEST_MESSAGE,
        signature=TEST_SIGNATURE_B64,
        verifying_key=TEST_VERIFYING_KEY_PEM,
    )
    assert call.execute()


def test_ecdsa_verification_call_invalid_signature():
    # Create an invalid signature
    invalid_signature = TEST_SIGNING_KEY.sign(
        b"Different message",
        hashfunc=ECDSAVerificationCall._hash_func,
        sigencode=sigencode_der,
    )
    invalid_signature_b64 = base64.b64encode(invalid_signature).decode("utf-8")

    call = TestECDSAVerificationCall(
        message=TEST_MESSAGE,
        signature=invalid_signature_b64,
        verifying_key=TEST_VERIFYING_KEY_PEM,
    )
    assert not call.execute()


def test_ecdsa_condition_missing_message():
    with pytest.raises(
        InvalidCondition, match="'message' field - Field may not be null."
    ):
        _ = ECDSACondition(message=None, signature=None, verifying_key=None)


def test_ecdsa_condition_missing_signature():
    with pytest.raises(
        InvalidCondition, match="'signature' field - Field may not be null."
    ):
        _ = ECDSACondition(
            message=":message_variable", signature=None, verifying_key=None
        )


def test_ecdsa_condition_missing_verifying_key():
    with pytest.raises(
        InvalidCondition, match="'verifying_key' field - Field may not be null."
    ):
        _ = ECDSACondition(
            message=":message_variable",
            signature=":signature_variable",
            verifying_key=None,
        )


def test_ecdsa_condition_invalid_verifying_key():
    with pytest.raises(
        InvalidCondition, match="'verifying_key' field - Invalid verifying key format"
    ):
        _ = ECDSACondition(
            message=":message_variable",
            signature=":signature_variable",
            verifying_key="-----BEGIN PUBLIC KEY----- invalid key -----END PUBLIC KEY-----",
        )


def test_ecdsa_condition_initialization():
    condition = ECDSACondition(
        message=":message_variable",
        signature=":signature_variable",
        verifying_key=TEST_VERIFYING_KEY_PEM,
    )

    assert condition.message == ":message_variable"
    assert condition.signature == ":signature_variable"
    assert condition.verifying_key == TEST_VERIFYING_KEY_PEM
    assert condition.condition_type == ECDSACondition.CONDITION_TYPE


def test_ecdsa_condition_verify():
    condition = ECDSACondition(
        message=":message_variable",
        signature=":signature_variable",
        verifying_key=TEST_VERIFYING_KEY_PEM,
    )

    context = {
        ":message_variable": TEST_MESSAGE,
        ":signature_variable": TEST_SIGNATURE_B64,
    }
    success, result = condition.verify(**context)
    assert success
    assert result is True


def test_ecdsa_condition_verify_invalid_signature():
    # Create an invalid signature
    invalid_signature = TEST_SIGNING_KEY.sign(
        b"Different message",
        hashfunc=ECDSAVerificationCall._hash_func,
        sigencode=sigencode_der,
    )
    invalid_signature_b64 = base64.b64encode(invalid_signature).decode("utf-8")

    condition = ECDSACondition(
        message=":message_variable",
        signature=":signature_variable",
        verifying_key=TEST_VERIFYING_KEY_PEM,
    )

    context = {
        ":message_variable": TEST_MESSAGE,
        ":signature_variable": invalid_signature_b64,
    }
    success, result = condition.verify(**context)
    assert not success
    assert result is False
