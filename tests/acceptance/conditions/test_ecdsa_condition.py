from ecdsa import NIST192p, SECP256k1, SigningKey
from ecdsa.util import sigencode_string

from nucypher.policy.conditions.ecdsa import ECDSACondition, ECDSAVerificationCall
from nucypher.policy.conditions.lingo import ConditionLingo

# Create test key pair for ECDSA signing
TEST_SIGNING_KEY = SigningKey.generate(curve=SECP256k1)
TEST_VERIFYING_KEY = TEST_SIGNING_KEY.verifying_key
TEST_VERIFYING_KEY_HEX = TEST_VERIFYING_KEY.to_string().hex()

# Test message
TEST_MESSAGE = "This is a test message that requires ECDSA verification"


def test_ecdsa_condition_verification_flow():
    """
    Test a practical flow where an ECDSA condition is used to verify a signature
    """
    # Sign the test message with the private key
    signature = TEST_SIGNING_KEY.sign(
        TEST_MESSAGE.encode("utf-8"),
        hashfunc=ECDSAVerificationCall._hash_func,
        sigencode=sigencode_string,
    ).hex()

    # Create an ECDSA condition using a regular context variable (not USER_ADDRESS_CONTEXT)
    ecdsa_condition = ECDSACondition(
        message=":message",  # Use regular context variable instead of USER_ADDRESS_CONTEXT
        signature=":signature",
        verifying_key=TEST_VERIFYING_KEY_HEX,
        curve=SECP256k1.name,
    )

    # Create a complete condition lingo
    condition_lingo = ConditionLingo(ecdsa_condition)

    # Set up the context for verification with regular context variables
    context = {":message": TEST_MESSAGE, ":signature": signature}

    # Evaluate the condition
    result = condition_lingo.eval(**context)
    assert result, "ECDSA signature verification should succeed with valid signature"

    # Test with an invalid signature
    # Sign a different message
    different_message = "Different message"
    invalid_signature = TEST_SIGNING_KEY.sign(
        different_message.encode("utf-8"),
        hashfunc=ECDSAVerificationCall._hash_func,
        sigencode=sigencode_string,
    ).hex()

    # Update context with invalid signature
    context[":signature"] = invalid_signature

    # Evaluate the condition again
    result = condition_lingo.eval(**context)
    assert not result, "ECDSA signature verification should fail with invalid signature"


def test_ecdsa_condition_in_compound_condition():
    """
    Test using an ECDSA condition in a compound condition with another condition
    """
    from nucypher.policy.conditions.lingo import (
        CompoundCondition,
        Operator,
    )

    # Sign the test message with the private key
    signature = TEST_SIGNING_KEY.sign(
        TEST_MESSAGE.encode("utf-8"),
        hashfunc=ECDSAVerificationCall._hash_func,
        sigencode=sigencode_string,
    ).hex()

    # Create an ECDSA condition
    ecdsa_condition = ECDSACondition(
        message=":message",
        signature=":signature",
        verifying_key=TEST_VERIFYING_KEY_HEX,
        curve=SECP256k1.name,
    )

    # Create a second ECDSA condition with different requirements
    second_signing_key = SigningKey.generate(curve=NIST192p)
    second_verifying_key = second_signing_key.verifying_key
    second_verifying_key_hex = second_verifying_key.to_string().hex()

    second_ecdsa_condition = ECDSACondition(
        message=":second_message",
        signature=":second_signature",
        verifying_key=second_verifying_key_hex,
        curve=NIST192p.name,
    )

    # Create a compound condition with OR operator
    compound_condition = CompoundCondition(
        operator=Operator.OR.value, operands=[ecdsa_condition, second_ecdsa_condition]
    )

    # Create a complete condition lingo
    condition_lingo = ConditionLingo(compound_condition)

    # Context with only the first signature valid
    second_message = "Second message"
    context = {
        ":message": TEST_MESSAGE,
        ":signature": signature,
        ":second_message": second_message,
        ":second_signature": "abcd1234",  # Invalid signature for second condition
    }

    # Compound OR condition should succeed if at least one condition is true
    result = condition_lingo.eval(**context)
    assert (
        result
    ), "Compound OR condition should succeed if at least one ECDSA verification is true"

    # Create a compound condition with AND operator
    compound_condition = CompoundCondition(
        operator=Operator.AND.value, operands=[ecdsa_condition, second_ecdsa_condition]
    )

    # Create a complete condition lingo
    condition_lingo = ConditionLingo(compound_condition)

    # Compound AND condition should fail if any condition is false
    result = condition_lingo.eval(**context)
    assert (
        not result
    ), "Compound AND condition should fail if any ECDSA verification is false"

    # Sign the second message properly
    second_signature = second_signing_key.sign(
        second_message.encode("utf-8"),
        hashfunc=ECDSAVerificationCall._hash_func,
        sigencode=sigencode_string,
    ).hex()

    # Update context with valid second signature
    context[":second_signature"] = second_signature

    # Compound AND condition should now succeed with both signatures valid
    result = condition_lingo.eval(**context)
    assert (
        result
    ), "Compound AND condition should succeed if all ECDSA verifications are true"
