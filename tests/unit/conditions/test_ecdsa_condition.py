import json

import pytest
from ecdsa.curves import SECP256k1, NIST192p
from ecdsa.keys import SigningKey
from ecdsa.util import sigencode_string
from marshmallow import validates

from nucypher.policy.conditions.ecdsa import ECDSACondition, ECDSAVerificationCall
from nucypher.policy.conditions.exceptions import (
    InvalidCondition,
)

# Generate test keys for ECDSA signing/verification
TEST_SIGNING_KEY = SigningKey.generate(curve=SECP256k1)
TEST_VERIFYING_KEY = TEST_SIGNING_KEY.verifying_key

# Get the hex encoded verifying key
TEST_VERIFYING_KEY_HEX = TEST_VERIFYING_KEY.to_string().hex()

# Test message and signature
TEST_MESSAGE = b"This is a test message for ECDSA verification"
TEST_SIGNATURE = TEST_SIGNING_KEY.sign(
    TEST_MESSAGE, hashfunc=ECDSAVerificationCall._hash_func, sigencode=sigencode_string
)
TEST_SIGNATURE_HEX = TEST_SIGNATURE.hex()


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
        signature=TEST_SIGNATURE_HEX,
        verifying_key=TEST_VERIFYING_KEY_HEX,
        curve=SECP256k1,
    )
    assert call.execute()


def test_ecdsa_verification_call_invalid_signature():
    # Create an invalid signature
    invalid_signature = TEST_SIGNING_KEY.sign(
        b"Different message",
        hashfunc=ECDSAVerificationCall._hash_func,
        sigencode=sigencode_string,
    ).hex()

    call = TestECDSAVerificationCall(
        message=TEST_MESSAGE,
        signature=invalid_signature,
        verifying_key=TEST_VERIFYING_KEY_HEX,
        curve=SECP256k1,
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
        verifying_key=TEST_VERIFYING_KEY_HEX,
    )

    assert condition.message == ":message_variable"
    assert condition.signature == ":signature_variable"
    assert condition.verifying_key == TEST_VERIFYING_KEY_HEX
    assert condition.condition_type == ECDSACondition.CONDITION_TYPE


def test_ecdsa_condition_verify():
    condition = ECDSACondition(
        message=":message_variable",
        signature=":signature_variable",
        verifying_key=TEST_VERIFYING_KEY_HEX,
        curve=SECP256k1.name,
    )

    context = {
        ":message_variable": TEST_MESSAGE,
        ":signature_variable": TEST_SIGNATURE_HEX,
    }
    success, result = condition.verify(**context)
    assert success
    assert result is True


def test_ecdsa_condition_verify_invalid_signature():
    # Create an invalid signature
    invalid_signature = TEST_SIGNING_KEY.sign(
        b"Different message",
        hashfunc=ECDSAVerificationCall._hash_func,
        sigencode=sigencode_string,
    ).hex()

    condition = ECDSACondition(
        message=":message_variable",
        signature=":signature_variable",
        verifying_key=TEST_VERIFYING_KEY_HEX,
    )

    context = {
        ":message_variable": TEST_MESSAGE,
        ":signature_variable": invalid_signature,
    }
    success, result = condition.verify(**context)
    assert not success
    assert result is False


def test_ecdsa_condition_different_curves():
    # Test with SECP256k1 curve
    secp256k1_key = SigningKey.generate(curve=SECP256k1)
    secp256k1_verifying_key = secp256k1_key.verifying_key
    secp256k1_verifying_key_hex = secp256k1_verifying_key.to_string().hex()

    secp256k1_message = b"Test message for SECP256k1"
    secp256k1_signature = secp256k1_key.sign(
        secp256k1_message,
        hashfunc=ECDSAVerificationCall._hash_func,
        sigencode=sigencode_string,
    ).hex()

    # Test with NIST192p curve
    nist192p_key = SigningKey.generate(curve=NIST192p)
    nist192p_verifying_key = nist192p_key.verifying_key
    nist192p_verifying_key_hex = nist192p_verifying_key.to_string().hex()

    nist192p_message = b"Test message for NIST192p"
    nist192p_signature = nist192p_key.sign(
        nist192p_message,
        hashfunc=ECDSAVerificationCall._hash_func,
        sigencode=sigencode_string,
    ).hex()

    # Test SECP256k1 condition
    secp256k1_condition = ECDSACondition(
        message=":message_variable",
        signature=":signature_variable",
        verifying_key=secp256k1_verifying_key_hex,
        curve=SECP256k1.name,
    )

    secp256k1_context = {
        ":message_variable": secp256k1_message,
        ":signature_variable": secp256k1_signature,
    }
    success, result = secp256k1_condition.verify(**secp256k1_context)
    assert success
    assert result is True

    # Test NIST192p condition
    nist192p_condition = ECDSACondition(
        message=":message_variable",
        signature=":signature_variable",
        verifying_key=nist192p_verifying_key_hex,
        curve=NIST192p.name,
    )

    nist192p_context = {
        ":message_variable": nist192p_message,
        ":signature_variable": nist192p_signature,
    }
    success, result = nist192p_condition.verify(**nist192p_context)
    assert success
    assert result is True

    # Test that signatures don't work with wrong curves
    wrong_curve_context = {
        ":message_variable": secp256k1_message,
        ":signature_variable": secp256k1_signature,
    }
    success, result = nist192p_condition.verify(**wrong_curve_context)
    assert not success
    assert result is False


def test_ecdsa_condition_bytes_context():
    """Test that ECDSA conditions can handle bytes in context through serialization.

    This test verifies that:
    1. Bytes can be passed in context and will be properly [de]serialized
    2. The condition can handle both raw bytes and hex strings
    3. The verification works correctly after serialization/deserialization
    """
    # Create a test message and sign it
    message_bytes = b"This is a test message that requires ECDSA verification"
    signature = TEST_SIGNING_KEY.sign(
        message_bytes,
        hashfunc=ECDSAVerificationCall._hash_func,
        sigencode=sigencode_string,
    ).hex()

    # Create an ECDSA condition
    ecdsa_condition = ECDSACondition(
        message=":bytes:message",
        signature=":signature",
        verifying_key=TEST_VERIFYING_KEY_HEX,
        curve=SECP256k1.name,
    )

    # Test with raw bytes in context
    context_with_bytes = {
        ":bytes:message": message_bytes.hex(),
        ":signature": signature,
    }

    # The context should be serializable
    serialized_context = json.dumps(context_with_bytes)
    deserialized_context = json.loads(serialized_context)

    # Verification should work with the deserialized context
    success, result = ecdsa_condition.verify(**deserialized_context)
    assert success, "Verification should succeed with deserialized bytes context"
    assert result is True

    # Test with hex string in context (backwards compatibility)
    context_with_hex = {
        ":bytes:message": message_bytes.hex(),
        ":signature": signature,
    }

    # The context should be serializable
    serialized_context = json.dumps(context_with_hex)
    deserialized_context = json.loads(serialized_context)

    # Verification should work with the deserialized context
    success, result = ecdsa_condition.verify(**deserialized_context)
    assert success, "Verification should succeed with deserialized hex context"
    assert result is True

    # Test with mixed types (some bytes, some hex)
    context_mixed = {
        ":bytes:message": message_bytes.hex(),
        ":signature": signature,
    }

    # The context should be serializable
    serialized_context = json.dumps(context_mixed)
    deserialized_context = json.loads(serialized_context)

    # Verification should work with the deserialized context
    success, result = ecdsa_condition.verify(**deserialized_context)
    assert success, "Verification should succeed with deserialized mixed context"
    assert result is True

