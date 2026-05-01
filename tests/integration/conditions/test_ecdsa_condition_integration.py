from ecdsa import Ed25519, SECP256k1, SigningKey
from ecdsa.util import sigencode_string

from nucypher.policy.conditions.ecdsa import ECDSACondition, ECDSAVerificationCall
from nucypher.policy.conditions.json.json import JsonCondition
from nucypher.policy.conditions.lingo import (
    AndCompoundCondition,
    CompoundCondition,
    ConditionLingo,
    ConditionVariable,
    ReturnValueTest,
    SequentialCondition,
    VariableOperation,
)
from nucypher.policy.conditions.utils import ConditionProviderManager
from nucypher.policy.conditions.var import ContextVariableCondition

# Create test key pair for ECDSA signing
TEST_SIGNING_KEY = SigningKey.generate(curve=SECP256k1)
TEST_VERIFYING_KEY = TEST_SIGNING_KEY.verifying_key
TEST_VERIFYING_KEY_HEX = TEST_VERIFYING_KEY.to_string().hex()

# Test message
TEST_MESSAGE = (
    "There is a road, no simple highway, between the dawn and the dark of night. -JG"
)

# Discord Ed25519 test vectors (shared across multiple tests)
DISCORD_PUBLIC_KEY_HEX = (
    "b853dd9f496723daf64bf2f5a886086f790df66e61d7b6f7f98a50c9e5ede8f3"
)
DISCORD_SIGNATURE_HEX = "0a12acb96843700b724f1c9dba3075a7fc482677e0c713eb6be63bfea406fb33b4715975f1062b2dff95127bd559ee23758911bd217760727dc44e7880bc6e04"
DISCORD_TIMESTAMP = "1749368683"
DISCORD_BODY = '{"app_permissions":"2248473465835073","application_id":"1380486651436073092","attachment_size_limit":10485760,"authorizing_integration_owners":{"0":"1380488052169769110"},"channel":{"flags":0,"guild_id":"1380488052169769110","icon_emoji":{"id":null,"name":"👋"},"id":"1380488052169769113","last_message_id":"1380528253168652328","name":"general","nsfw":false,"parent_id":"1380488052169769111","permissions":"2251799813685247","position":0,"rate_limit_per_user":0,"theme_color":null,"topic":null,"type":0},"channel_id":"1380488052169769113","context":0,"data":{"id":"1380515955146358918","name":"sign","options":[{"name":"message","type":3,"value":"llamas"}],"type":1},"entitlement_sku_ids":[],"entitlements":[],"guild":{"features":[],"id":"1380488052169769110","locale":"en-US"},"guild_id":"1380488052169769110","guild_locale":"en-US","id":"1381177107555680327","locale":"en-US","member":{"avatar":null,"banner":null,"communication_disabled_until":null,"deaf":false,"flags":0,"joined_at":"2025-06-06T10:06:39.888000+00:00","mute":false,"nick":null,"pending":false,"permissions":"2251799813685247","premium_since":null,"roles":[],"unusual_dm_activity_until":null,"user":{"avatar":"9c5483a989a10edc8b831b6c8f284724","avatar_decoration_data":null,"clan":null,"collectibles":null,"discriminator":"0","global_name":"kprasch","id":"410212090289192960","primary_guild":null,"public_flags":0,"username":"kprasch"}},"token":"aW50ZXJhY3Rpb246MTM4MTE3NzEwNzU1NTY4MDMyNzo2ZlVlTkdIQVFIdkdhNUN2bXlYZ1RCRkZ5YkpuVm9WUG5Bbjl0TTMyUkFTenZGYXNXclBCMjZWUWJlalczcllRak9sc0JZR3Q4WW9sODBRcDg2c2hrYmRkYzlWcjF3TjdlRFVDMVBVTkZ3Z2VmRUp4VkI1MkZGNmVvM3hkWXd1Qg","type":2,"version":1}'


def test_ecdsa_lingo_basic_verification():
    """Test a basic ECDSA verification using condition lingo"""
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
        curve=SECP256k1.name,
    )

    # Create condition lingo
    lingo = ConditionLingo(ecdsa_condition)

    # Valid context
    context = {":message": TEST_MESSAGE, ":signature": signature}
    result = lingo.eval(**context)
    assert result is True

    # Invalid signature
    different_message = b"Different message"
    invalid_signature = TEST_SIGNING_KEY.sign(
        different_message,
        hashfunc=ECDSAVerificationCall._hash_func,
        sigencode=sigencode_string,
    ).hex()

    context[":signature"] = invalid_signature
    result = lingo.eval(**context)
    assert result is False


def test_ecdsa_in_compound_condition():
    """Test ECDSA as part of a compound condition"""
    # Sign the message
    signature = TEST_SIGNING_KEY.sign(
        TEST_MESSAGE.encode("utf-8"),
        hashfunc=ECDSAVerificationCall._hash_func,
        sigencode=sigencode_string,
    ).hex()

    # Create two ECDSA conditions
    ecdsa_condition1 = ECDSACondition(
        message=":message1",
        signature=":signature1",
        verifying_key=TEST_VERIFYING_KEY_HEX,
        curve=SECP256k1.name,
    )

    # Create a second key pair
    second_key = SigningKey.generate(curve=SECP256k1)
    second_verifying_key = second_key.verifying_key
    second_verifying_key_hex = second_verifying_key.to_string().hex()

    ecdsa_condition2 = ECDSACondition(
        message=":message2",
        signature=":signature2",
        verifying_key=second_verifying_key_hex,
        curve=SECP256k1.name,
    )

    # Create OR compound condition
    or_condition = CompoundCondition(
        operator="or", operands=[ecdsa_condition1, ecdsa_condition2]
    )

    # Create AND compound condition
    and_condition = CompoundCondition(
        operator="and", operands=[ecdsa_condition1, ecdsa_condition2]
    )

    # Create lingos
    or_lingo = ConditionLingo(or_condition)
    and_lingo = ConditionLingo(and_condition)

    # Sign a message with the second key
    second_message = "Second message"
    second_signature = second_key.sign(
        second_message.encode("utf-8"),
        hashfunc=ECDSAVerificationCall._hash_func,
        sigencode=sigencode_string,
    ).hex()

    # Test case: first signature valid, second invalid
    context = {
        ":message1": TEST_MESSAGE,
        ":signature1": signature,
        ":message2": "Not the correct message",
        ":signature2": second_signature,
    }

    # OR condition should succeed if at least one is valid
    assert or_lingo.eval(**context) is True

    # AND condition should fail if any is invalid
    assert and_lingo.eval(**context) is False

    # Update context with valid second message
    context[":message2"] = second_message

    # Now both conditions are valid, so AND should pass
    assert and_lingo.eval(**context) is True


def test_discord_json_from_body_string():
    """Test parsing Discord body JSON string directly from context variable with 3-variable context"""
    # Use Discord Ed25519 test vectors
    public_key_hex = DISCORD_PUBLIC_KEY_HEX
    signature_hex = DISCORD_SIGNATURE_HEX
    timestamp = DISCORD_TIMESTAMP

    # This is the raw JSON string as it would come from Discord
    body = DISCORD_BODY

    # Create ECDSA condition for signature verification with message template
    ecdsa_condition = ECDSACondition(
        message=":timestamp:discordPayload",  # Constructs message from timestamp + payload
        signature=":signature",
        verifying_key=public_key_hex,
        curve=Ed25519.name,
    )

    # Create JSON condition that parses the raw JSON string from context
    # This demonstrates that JsonCondition can handle JSON strings directly
    json_command_value = JsonCondition(
        data=":discordPayload",  # Context variable containing JSON string
        query="$.data.options[0].value",  # Extract the command value ("llamas")
        return_value_test=ReturnValueTest("==", "'llamas'"),
    )

    # Create another JSON condition to check the username
    json_username = JsonCondition(
        data=":discordPayload",  # Same JSON string
        query="$.member.user.username",
        return_value_test=ReturnValueTest("==", "'kprasch'"),
    )

    # Compound condition: Both signature AND command value must be valid
    signature_and_command = AndCompoundCondition(
        operands=[ecdsa_condition, json_command_value]
    )

    # Context with only 3 variables
    context = {
        ":timestamp": timestamp,
        ":discordPayload": body,  # Pass the raw JSON string
        ":signature": signature_hex,
    }

    # Test the compound condition
    lingo = ConditionLingo(signature_and_command)
    result = lingo.eval(**context)
    assert (
        result is True
    ), "Signature verification + JSON parsing from string should pass"

    # Create a more complex compound: signature AND (command value AND username)
    complex_compound = AndCompoundCondition(
        operands=[
            ecdsa_condition,
            AndCompoundCondition(operands=[json_command_value, json_username]),
        ]
    )

    lingo_complex = ConditionLingo(complex_compound)
    result = lingo_complex.eval(**context)
    assert (
        result is True
    ), "Complex nested condition with JSON string parsing should pass"

    # Test failure when JSON value doesn't match
    json_wrong_value = JsonCondition(
        data=":discordPayload",
        query="$.data.options[0].value",
        return_value_test=ReturnValueTest("==", "'alpacas'"),  # Wrong value
    )

    wrong_compound = AndCompoundCondition(operands=[ecdsa_condition, json_wrong_value])

    lingo_wrong = ConditionLingo(wrong_compound)
    result = lingo_wrong.eval(**context)
    assert result is False, "Should fail when JSON value doesn't match expected"

    # Test extracting numeric values from the JSON
    json_attachment_limit = JsonCondition(
        data=":discordPayload",
        query="$.attachment_size_limit",
        return_value_test=ReturnValueTest(">", 1000000),  # Check it's > 1MB
    )

    numeric_compound = AndCompoundCondition(
        operands=[ecdsa_condition, json_attachment_limit]
    )

    lingo_numeric = ConditionLingo(numeric_compound)
    result = lingo_numeric.eval(**context)
    assert result is True, "Numeric comparison from JSON should work"


def test_discord_with_sequential_concatenation():
    """Test using Sequential condition to concatenate timestamp and payload in-lingo"""
    # Use Discord Ed25519 test vectors
    public_key_hex = DISCORD_PUBLIC_KEY_HEX
    signature_hex = DISCORD_SIGNATURE_HEX
    timestamp = DISCORD_TIMESTAMP
    body = DISCORD_BODY

    # ===== Method 1: Sequential condition to concatenate timestamp + discordPayload =====
    # Create a Sequential condition that:
    # 1. Gets the timestamp from context
    # 2. Concatenates it with discordPayload using += operator
    # 3. Stores result as :message for ECDSA to use

    # Step 1: Get timestamp from context
    timestamp_condition = ContextVariableCondition(
        context_variable=":timestamp", return_value_test=ReturnValueTest("!=", "''")
    )

    # Step 2: Create a condition variable that gets timestamp and concatenates with payload
    message_builder = ConditionVariable(
        var_name="message",  # This will be available as :message
        condition=timestamp_condition,
        operations=[
            # Use += operator to concatenate the discordPayload
            VariableOperation(operation="+=", value=":discordPayload")
        ],
    )

    # Step 3: Add a JSON condition as second variable (to meet minimum 2 variables)
    # This parses and validates the Discord payload
    json_check_var = ConditionVariable(
        var_name="commandValue",
        condition=JsonCondition(
            data=":discordPayload",
            query="$.data.options[0].value",
            return_value_test=ReturnValueTest("==", "'llamas'"),
        ),
    )

    # Now create ECDSA condition that uses the concatenated message
    ecdsa_var = ConditionVariable(
        var_name="signatureValid",
        condition=ECDSACondition(
            message=":message",  # Uses the result from sequential condition
            signature=":signature",
            verifying_key=public_key_hex,
            curve=Ed25519.name,
        ),
    )

    # Create the sequential condition with all 3 variables:
    # 1. Build message from timestamp + payload
    # 2. Parse and validate JSON command value
    # 3. Verify ECDSA signature
    sequential = SequentialCondition(
        condition_variables=[message_builder, json_check_var, ecdsa_var]
    )

    # Context with only 3 variables
    context = {
        ":timestamp": timestamp,
        ":discordPayload": body,
        ":signature": signature_hex,
    }

    # Sequential conditions require providers argument
    result, _ = sequential.verify(providers=ConditionProviderManager({}), **context)
    assert result is True, "Sequential concatenation + ECDSA should work"

    # ===== Method 2: Multiple operations to build formatted message =====
    # This demonstrates building a more complex string with multiple concatenations

    # Build message with operations: timestamp + separator + payload
    formatted_message_builder = ConditionVariable(
        var_name="formattedMessage",
        condition=timestamp_condition,  # Reuse the timestamp condition from method 1
        operations=[
            # Can add multiple concatenations (up to 5 operations max)
            VariableOperation(operation="+=", value=":discordPayload"),
            # Could add more transformations if needed:
            # VariableOperation(operation="str"),  # Ensure it's a string
        ],
    )

    # Add ECDSA verification as second variable
    ecdsa_formatted_var = ConditionVariable(
        var_name="signatureValid2",
        condition=ECDSACondition(
            message=":formattedMessage",
            signature=":signature",
            verifying_key=public_key_hex,
            curve=Ed25519.name,
        ),
    )

    sequential_formatted = SequentialCondition(
        condition_variables=[formatted_message_builder, ecdsa_formatted_var]
    )

    result_formatted, _ = sequential_formatted.verify(
        providers=ConditionProviderManager({}), **context
    )
    assert result_formatted is True, "Formatted message concatenation should work"

    # ===== Method 3: Sequential with JSON parsing =====
    # Concatenate message, then also parse JSON from discordPayload

    # First build the message (reuse timestamp_condition)
    message_var_3 = ConditionVariable(
        var_name="message",
        condition=timestamp_condition,  # Reuse the timestamp condition
        operations=[VariableOperation(operation="+=", value=":discordPayload")],
    )

    # Then parse a value from the JSON payload
    json_value_var = ConditionVariable(
        var_name="commandValue",
        condition=JsonCondition(
            data=":discordPayload",
            query="$.data.options[0].value",
            return_value_test=ReturnValueTest("==", "'llamas'"),
        ),
    )

    # ECDSA using the built message
    ecdsa_with_json_var = ConditionVariable(
        var_name="signatureValid3",
        condition=ECDSACondition(
            message=":message",
            signature=":signature",
            verifying_key=public_key_hex,
            curve=Ed25519.name,
        ),
    )

    # Sequential condition that does all three:
    # 1. Build message from timestamp + payload
    # 2. Parse and validate JSON command value
    # 3. Verify ECDSA signature
    sequential_with_json = SequentialCondition(
        condition_variables=[message_var_3, json_value_var, ecdsa_with_json_var]
    )

    result_with_json, _ = sequential_with_json.verify(
        providers=ConditionProviderManager({}), **context
    )
    assert (
        result_with_json is True
    ), "Sequential with message building and JSON parsing should work"

    # Test failure case - wrong signature
    wrong_context = context.copy()
    wrong_context[":signature"] = "0" * len(signature_hex)

    result_fail, _ = sequential.verify(
        providers=ConditionProviderManager({}), **wrong_context
    )
    assert result_fail is False, "Should fail with invalid signature"
