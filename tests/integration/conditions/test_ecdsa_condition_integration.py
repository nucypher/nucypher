import base64

from ecdsa import SECP256k1, SigningKey
from ecdsa.util import sigencode_string

from nucypher.policy.conditions.ecdsa import ECDSACondition, ECDSAVerificationCall
from nucypher.policy.conditions.lingo import (
    CompoundAccessControlCondition,
    ConditionLingo,
)

# Create test key pair for ECDSA signing
TEST_SIGNING_KEY = SigningKey.generate(curve=SECP256k1)
TEST_VERIFYING_KEY = TEST_SIGNING_KEY.verifying_key
TEST_VERIFYING_KEY_PEM = TEST_VERIFYING_KEY.to_pem().decode("utf-8")

# Test message
TEST_MESSAGE = b"This is a test message that requires ECDSA verification"


def test_ecdsa_lingo_basic_verification():
    """Test a basic ECDSA verification using condition lingo"""
    # Sign the test message
    signature = TEST_SIGNING_KEY.sign(
        TEST_MESSAGE,
        hashfunc=ECDSAVerificationCall._hash_func,
        sigencode=sigencode_string,
    )
    signature_b64 = base64.b64encode(signature).decode("utf-8")

    # Create condition
    ecdsa_condition = ECDSACondition(
        message=":message",
        signature=":signature",
        verifying_key=TEST_VERIFYING_KEY_PEM,
    )

    # Create condition lingo
    lingo = ConditionLingo(ecdsa_condition)

    # Valid context
    context = {":message": TEST_MESSAGE, ":signature": signature_b64}
    result = lingo.eval(**context)
    assert result is True

    # Invalid signature
    different_message = b"Different message"
    invalid_signature = TEST_SIGNING_KEY.sign(
        different_message,
        hashfunc=ECDSAVerificationCall._hash_func,
        sigencode=sigencode_string,
    )
    invalid_signature_b64 = base64.b64encode(invalid_signature).decode("utf-8")

    context[":signature"] = invalid_signature_b64
    result = lingo.eval(**context)
    assert result is False


def test_ecdsa_in_compound_condition():
    """Test ECDSA as part of a compound condition"""
    # Sign the message
    signature = TEST_SIGNING_KEY.sign(
        TEST_MESSAGE,
        hashfunc=ECDSAVerificationCall._hash_func,
        sigencode=sigencode_string,
    )
    signature_b64 = base64.b64encode(signature).decode("utf-8")

    # Create two ECDSA conditions
    ecdsa_condition1 = ECDSACondition(
        message=":message1",
        signature=":signature1",
        verifying_key=TEST_VERIFYING_KEY_PEM,
    )

    # Create a second key pair
    second_key = SigningKey.generate(curve=SECP256k1)
    second_verifying_key = second_key.verifying_key
    second_verifying_key_pem = second_verifying_key.to_pem().decode("utf-8")

    ecdsa_condition2 = ECDSACondition(
        message=":message2",
        signature=":signature2",
        verifying_key=second_verifying_key_pem,
    )

    # Create OR compound condition
    or_condition = CompoundAccessControlCondition(
        operator="or", operands=[ecdsa_condition1, ecdsa_condition2]
    )

    # Create AND compound condition
    and_condition = CompoundAccessControlCondition(
        operator="and", operands=[ecdsa_condition1, ecdsa_condition2]
    )

    # Create lingos
    or_lingo = ConditionLingo(or_condition)
    and_lingo = ConditionLingo(and_condition)

    # Sign a message with the second key
    second_message = b"Second message"
    second_signature = second_key.sign(
        second_message,
        hashfunc=ECDSAVerificationCall._hash_func,
        sigencode=sigencode_string,
    )
    second_signature_b64 = base64.b64encode(second_signature).decode("utf-8")

    # Test case: first signature valid, second invalid
    context = {
        ":message1": TEST_MESSAGE,
        ":signature1": signature_b64,
        ":message2": b"Not the correct message",
        ":signature2": second_signature_b64,
    }

    # OR condition should succeed if at least one is valid
    assert or_lingo.eval(**context) is True

    # AND condition should fail if any is invalid
    assert and_lingo.eval(**context) is False

    # Update context with valid second message
    context[":message2"] = second_message

    # Now both conditions are valid, so AND should pass
    assert and_lingo.eval(**context) is True
