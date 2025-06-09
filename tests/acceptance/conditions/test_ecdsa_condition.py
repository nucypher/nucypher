import base64

from ecdsa import SECP256k1, SigningKey
from ecdsa.util import sigencode_der

from nucypher.policy.conditions.context import USER_ADDRESS_CONTEXT
from nucypher.policy.conditions.ecdsa import ECDSACondition, ECDSAVerificationCall
from nucypher.policy.conditions.lingo import ConditionLingo

# Create test key pair for ECDSA signing
TEST_SIGNING_KEY = SigningKey.generate()
TEST_VERIFYING_KEY = TEST_SIGNING_KEY.verifying_key
TEST_VERIFYING_KEY_PEM = TEST_VERIFYING_KEY.to_pem().decode("utf-8")

# Test message
TEST_MESSAGE = b"This is a test message that requires ECDSA verification"


def test_ecdsa_condition_verification_flow():
    """
    Test a practical flow where an ECDSA condition is used to verify a signature
    """
    # Sign the test message with the private key
    signature = TEST_SIGNING_KEY.sign(
        TEST_MESSAGE, hashfunc=ECDSAVerificationCall._hash_func, sigencode=sigencode_der
    )
    signature_b64 = base64.b64encode(signature).decode("utf-8")

    # Create an ECDSA condition
    ecdsa_condition = ECDSACondition(
        message=USER_ADDRESS_CONTEXT,
        signature=":signature",
        verifying_key=TEST_VERIFYING_KEY_PEM,
    )

    # Create a complete condition lingo
    condition_lingo = ConditionLingo(ecdsa_condition)

    # Set up the context for verification
    context = {USER_ADDRESS_CONTEXT: TEST_MESSAGE, ":signature": signature_b64}

    # Evaluate the condition
    result = condition_lingo.eval(**context)
    assert result, "ECDSA signature verification should succeed with valid signature"

    # Test with an invalid signature
    # Sign a different message
    different_message = b"Different message"
    invalid_signature = TEST_SIGNING_KEY.sign(
        different_message,
        hashfunc=ECDSAVerificationCall._hash_func,
        sigencode=sigencode_der,
    )
    invalid_signature_b64 = base64.b64encode(invalid_signature).decode("utf-8")

    # Update context with invalid signature
    context[":signature"] = invalid_signature_b64

    # Evaluate the condition again
    result = condition_lingo.eval(**context)
    assert not result, "ECDSA signature verification should fail with invalid signature"


def test_ecdsa_condition_in_compound_condition():
    """
    Test using an ECDSA condition in a compound condition with another condition
    """
    from nucypher.policy.conditions.lingo import (
        CompoundAccessControlCondition,
        Operator,
    )

    # Sign the test message with the private key
    signature = TEST_SIGNING_KEY.sign(
        TEST_MESSAGE, hashfunc=ECDSAVerificationCall._hash_func, sigencode=sigencode_der
    )
    signature_b64 = base64.b64encode(signature).decode("utf-8")

    # Create an ECDSA condition
    ecdsa_condition = ECDSACondition(
        message=USER_ADDRESS_CONTEXT,
        signature=":signature",
        verifying_key=TEST_VERIFYING_KEY_PEM,
    )

    # Create a second ECDSA condition with different requirements
    second_signing_key = SigningKey.generate(curve=SECP256k1)
    second_verifying_key = second_signing_key.verifying_key
    second_verifying_key_pem = second_verifying_key.to_pem().decode("utf-8")

    second_ecdsa_condition = ECDSACondition(
        message=":second_message",
        signature=":second_signature",
        verifying_key=second_verifying_key_pem,
    )

    # Create a compound condition with OR operator
    compound_condition = CompoundAccessControlCondition(
        operator=Operator.OR.value, operands=[ecdsa_condition, second_ecdsa_condition]
    )

    # Create a complete condition lingo
    condition_lingo = ConditionLingo(compound_condition)

    # Context with only the first signature valid
    context = {
        USER_ADDRESS_CONTEXT: TEST_MESSAGE,
        ":signature": signature_b64,
        ":second_message": b"Second message",
        ":second_signature": "invalid_signature",  # Invalid signature for second condition
    }

    # Compound OR condition should succeed if at least one condition is true
    result = condition_lingo.eval(**context)
    assert (
        result
    ), "Compound OR condition should succeed if at least one ECDSA verification is true"

    # Create a compound condition with AND operator
    compound_condition = CompoundAccessControlCondition(
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
        b"Second message",
        hashfunc=ECDSAVerificationCall._hash_func,
        sigencode=sigencode_der,
    )
    second_signature_b64 = base64.b64encode(second_signature).decode("utf-8")

    # Update context with valid second signature
    context[":second_signature"] = second_signature_b64

    # Compound AND condition should now succeed with both signatures valid
    result = condition_lingo.eval(**context)
    assert (
        result
    ), "Compound AND condition should succeed if all ECDSA verifications are true"
