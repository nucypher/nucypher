import json

from ecdsa import SigningKey
from ecdsa.util import sigencode_string
from hexbytes import HexBytes

from nucypher.policy.conditions.ecdsa import ECDSACondition, ECDSAVerificationCall
from nucypher.policy.conditions.lingo import (
    CompoundCondition,
    ConditionLingo,
)

# Create test key pair for ECDSA signing
TEST_SIGNING_KEY = SigningKey.generate()
TEST_VERIFYING_KEY = TEST_SIGNING_KEY.verifying_key
TEST_VERIFYING_KEY_HEX = TEST_VERIFYING_KEY.to_string().hex()

# Test message
TEST_MESSAGE = "This is a test message that requires ECDSA verification"


def test_ecdsa_condition_json_serialization():
    """Test serializing and deserializing ECDSA conditions to/from JSON"""
    # Sign the test message
    signature = TEST_SIGNING_KEY.sign(
        TEST_MESSAGE.encode("utf-8"),
        hashfunc=ECDSAVerificationCall._hash_func,
        sigencode=sigencode_string,
    ).hex()

    # Create condition
    ecdsa_condition = ECDSACondition(
        message=":message",
        signature=":signature",
        verifying_key=TEST_VERIFYING_KEY_HEX,
    )

    # Convert condition to JSON
    condition_json = ecdsa_condition.to_json()

    # Parse JSON to dict and verify structure
    condition_dict = json.loads(condition_json)
    assert condition_dict["conditionType"] == "ecdsa"
    assert condition_dict["message"] == ":message"
    assert condition_dict["signature"] == ":signature"
    assert condition_dict["verifyingKey"] == TEST_VERIFYING_KEY_HEX

    # Recreate condition from JSON
    recreated_condition = ECDSACondition.from_json(condition_json)

    # Verify the recreated condition
    assert recreated_condition.message == ":message"
    assert recreated_condition.signature == ":signature"
    assert recreated_condition.verifying_key == TEST_VERIFYING_KEY_HEX

    # Check that the recreated condition works
    context = {":message": TEST_MESSAGE, ":signature": signature}
    success, result = recreated_condition.verify(**context)
    assert success is True


def test_ecdsa_condition_lingo_json_serialization():
    """Test serializing and deserializing a condition lingo with ECDSA condition"""
    # Sign the test message
    signature = TEST_SIGNING_KEY.sign(
        TEST_MESSAGE.encode("utf-8"),
        hashfunc=ECDSAVerificationCall._hash_func,
        sigencode=sigencode_string,
    ).hex()

    # Create condition
    ecdsa_condition = ECDSACondition(
        message=":message",
        signature=":signature",
        verifying_key=TEST_VERIFYING_KEY_HEX,
    )

    # Create condition lingo
    lingo = ConditionLingo(ecdsa_condition)

    # Convert lingo to JSON
    lingo_json = lingo.to_json()

    # Parse JSON to dict and verify structure
    lingo_dict = json.loads(lingo_json)
    assert lingo_dict["version"] == ConditionLingo.VERSION
    assert lingo_dict["condition"]["conditionType"] == "ecdsa"

    # Recreate lingo from JSON
    recreated_lingo = ConditionLingo.from_json(lingo_json)

    # Verify the recreated lingo works
    context = {":message": TEST_MESSAGE, ":signature": signature}
    result = recreated_lingo.eval(**context)
    assert result is True


def test_complex_condition_with_ecdsa_json_serialization():
    """Test a complex condition with ECDSA JSON serialization"""
    # Create two key pairs for the test
    key1 = TEST_SIGNING_KEY
    key1_vk_hex = TEST_VERIFYING_KEY_HEX

    key2 = SigningKey.generate()
    key2_vk = key2.verifying_key
    key2_vk_hex = key2_vk.to_string().hex()

    # Sign the messages
    message1 = "Message for first key"
    message2 = "Message for second key"

    sig1 = key1.sign(
        message1.encode("utf-8"),
        hashfunc=ECDSAVerificationCall._hash_func,
        sigencode=sigencode_string,
    ).hex()

    sig2 = key2.sign(
        message2.encode("utf-8"),
        hashfunc=ECDSAVerificationCall._hash_func,
        sigencode=sigencode_string,
    ).hex()

    # Create ECDSA conditions
    condition1 = ECDSACondition(
        message=":msg1",
        signature=":sig1",
        verifying_key=key1_vk_hex,
        name="First Signer",
    )

    condition2 = ECDSACondition(
        message=":msg2",
        signature=":sig2",
        verifying_key=key2_vk_hex,
        name="Second Signer",
    )

    # Create compound condition (both signers must sign)
    compound_condition = CompoundCondition(
        operator="and", operands=[condition1, condition2], name="Both Signers Required"
    )

    # Convert to JSON
    json_condition = compound_condition.to_json()

    # Show what a typical JSON condition looks like (for documentation)
    expected_structure = {
        "name": "Both Signers Required",
        "conditionType": "compound",
        "operator": "and",
        "operands": [
            {
                "name": "First Signer",
                "conditionType": "ecdsa",
                "message": ":msg1",
                "signature": ":sig1",
                "verifyingKey": key1_vk_hex,
            },
            {
                "name": "Second Signer",
                "conditionType": "ecdsa",
                "message": ":msg2",
                "signature": ":sig2",
                "verifyingKey": key2_vk_hex,
            },
        ],
    }

    # Verify the structure matches expected pattern
    parsed_json = json.loads(json_condition)
    assert parsed_json["name"] == expected_structure["name"]
    assert parsed_json["conditionType"] == expected_structure["conditionType"]
    assert parsed_json["operator"] == expected_structure["operator"]
    assert len(parsed_json["operands"]) == 2

    # Recreate from JSON
    recreated_condition = CompoundCondition.from_json(json_condition)

    # Create a context with valid signatures
    context = {
        ":msg1": HexBytes(message1.encode("utf-8")).hex(),
        ":sig1": sig1,
        ":msg2": HexBytes(message2.encode("utf-8")).hex(),
        ":sig2": sig2,
    }

    # Verify the condition
    success, _ = recreated_condition.verify(**context)
    assert success is True

    # Test with invalid second signature (sign different message)
    invalid_sig2 = key2.sign(
        b"Wrong message",
        hashfunc=ECDSAVerificationCall._hash_func,
        sigencode=sigencode_string,
    ).hex()

    context[":sig2"] = invalid_sig2
    success, _ = recreated_condition.verify(**context)
    assert success is False


def test_real_world_example_json():
    """A realistic example showing how ECDSA condition might be used in a real application"""
    # This example demonstrates a policy that requires:
    # - An ECDSA signature from an authorized key
    # - In a compound condition with other potential access methods

    # Create a sample service key for verification
    service_key = SigningKey.generate()
    service_vk = service_key.verifying_key
    service_vk_hex = service_vk.to_string().hex()

    # JSON representation of the condition - this is what would typically
    # be stored in a database or config file
    condition_json = json.dumps(
        {
            "version": "1.0.0",
            "condition": {
                "conditionType": "compound",
                "operator": "or",
                "operands": [
                    # Option 1: Valid ECDSA signature
                    {
                        "conditionType": "ecdsa",
                        "name": "API Key Signature",
                        "message": ":request_data",
                        "signature": ":request_signature",
                        "verifyingKey": service_vk_hex,
                    },
                    # Option 2: Could combine with other conditions
                    # (e.g., a time-based condition as a fallback)
                    {
                        "conditionType": "compound",
                        "operator": "and",
                        "operands": [
                            {
                                "conditionType": "ecdsa",
                                "name": "Admin Signature",
                                "message": ":admin_request",
                                "signature": ":admin_signature",
                                "verifyingKey": TEST_VERIFYING_KEY_HEX,
                            },
                            # Add a second condition to satisfy the minimum requirement
                            {
                                "conditionType": "ecdsa",
                                "name": "Extra Verification",
                                "message": ":admin_request",
                                "signature": ":admin_signature",
                                "verifyingKey": TEST_VERIFYING_KEY_HEX,
                            },
                        ],
                    },
                ],
            },
        }
    )

    # Create lingo from JSON
    lingo = ConditionLingo.from_json(condition_json)

    # ---- Scenario 1: API user with valid signature ----
    request_data = '{"action": "read", "resource": "secret-data-123"}'
    request_signature = service_key.sign(
        request_data.encode("utf-8"),
        hashfunc=ECDSAVerificationCall._hash_func,
        sigencode=sigencode_string,
    ).hex()

    context = {
        ":request_data": HexBytes(request_data.encode("utf-8")).hex(),
        ":request_signature": request_signature,
    }

    # Evaluate condition
    result = lingo.eval(**context)
    assert result is True, "Valid API signature should grant access"

    # ---- Scenario 2: Admin access route ----
    admin_request = '{"action": "admin", "operation": "grant-access"}'
    admin_signature = TEST_SIGNING_KEY.sign(
        admin_request.encode("utf-8"),
        hashfunc=ECDSAVerificationCall._hash_func,
        sigencode=sigencode_string,
    ).hex()

    context = {
        # API key authentication fails
        ":request_data": request_data,
        ":request_signature": "abcd1234",  # invalid signature
        # But admin authentication succeeds
        ":admin_request": admin_request,
        ":admin_signature": admin_signature,
    }

    result = lingo.eval(**context)
    assert result is True, "Valid admin signature should grant access"

    # ---- Scenario 3: All authentication methods fail ----
    context = {
        ":request_data": request_data,
        ":request_signature": "aaaaaaaa",  # Invalid signature
        ":admin_request": admin_request,
        ":admin_signature": "bbbbbbbb",  # Invalid admin signature
    }

    result = lingo.eval(**context)
    assert result is False, "No valid authentication should deny access"
