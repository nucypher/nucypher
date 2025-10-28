import json

from ecdsa import Ed25519, SECP256k1, SigningKey
from ecdsa.util import sigencode_string
from hexbytes import HexBytes

from nucypher.policy.conditions.ecdsa import ECDSACondition, ECDSAVerificationCall
from nucypher.policy.conditions.json.json import JsonCondition
from nucypher.policy.conditions.lingo import (
    AndCompoundCondition,
    CompoundCondition,
    ConditionLingo,
    OrCompoundCondition,
    ReturnValueTest,
)

# Create test key pair for ECDSA signing
TEST_SIGNING_KEY = SigningKey.generate(curve=SECP256k1)
TEST_VERIFYING_KEY = TEST_SIGNING_KEY.verifying_key
TEST_VERIFYING_KEY_HEX = TEST_VERIFYING_KEY.to_string().hex()

# Test message
TEST_MESSAGE = (
    "There is a road, no simple highway, between the dawn and the dark of night. -JG"
)


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


def test_discord_ed25519_with_ecdsa_condition():
    # Discord Ed25519 test vector
    public_key_hex = "b853dd9f496723daf64bf2f5a886086f790df66e61d7b6f7f98a50c9e5ede8f3"
    signature_hex = "0a12acb96843700b724f1c9dba3075a7fc482677e0c713eb6be63bfea406fb33b4715975f1062b2dff95127bd559ee23758911bd217760727dc44e7880bc6e04"
    timestamp = "1749368683"
    body = '{"app_permissions":"2248473465835073","application_id":"1380486651436073092","attachment_size_limit":10485760,"authorizing_integration_owners":{"0":"1380488052169769110"},"channel":{"flags":0,"guild_id":"1380488052169769110","icon_emoji":{"id":null,"name":"👋"},"id":"1380488052169769113","last_message_id":"1380528253168652328","name":"general","nsfw":false,"parent_id":"1380488052169769111","permissions":"2251799813685247","position":0,"rate_limit_per_user":0,"theme_color":null,"topic":null,"type":0},"channel_id":"1380488052169769113","context":0,"data":{"id":"1380515955146358918","name":"sign","options":[{"name":"message","type":3,"value":"llamas"}],"type":1},"entitlement_sku_ids":[],"entitlements":[],"guild":{"features":[],"id":"1380488052169769110","locale":"en-US"},"guild_id":"1380488052169769110","guild_locale":"en-US","id":"1381177107555680327","locale":"en-US","member":{"avatar":null,"banner":null,"communication_disabled_until":null,"deaf":false,"flags":0,"joined_at":"2025-06-06T10:06:39.888000+00:00","mute":false,"nick":null,"pending":false,"permissions":"2251799813685247","premium_since":null,"roles":[],"unusual_dm_activity_until":null,"user":{"avatar":"9c5483a989a10edc8b831b6c8f284724","avatar_decoration_data":null,"clan":null,"collectibles":null,"discriminator":"0","global_name":"kprasch","id":"410212090289192960","primary_guild":null,"public_flags":0,"username":"kprasch"}},"token":"aW50ZXJhY3Rpb246MTM4MTE3NzEwNzU1NTY4MDMyNzo2ZlVlTkdIQVFIdkdhNUN2bXlYZ1RCRkZ5YkpuVm9WUG5Bbjl0TTMyUkFTenZGYXNXclBCMjZWUWJlalczcllRak9sc0JZR3Q4WW9sODBRcDg2c2hrYmRkYzlWcjF3TjdlRFVDMVBVTkZ3Z2VmRUp4VkI1MkZGNmVvM3hkWXd1Qg","type":2,"version":1}'

    # ===== PART 1: Original test - ECDSA only with new context structure =====
    # Create ECDSACondition that constructs message from timestamp + discordPayload
    ecdsa_condition = ECDSACondition(
        message=":timestamp:discordPayload",  # Message template concatenates these two
        signature=":signature",
        verifying_key=public_key_hex,
        curve=Ed25519.name,
    )

    # Create condition lingo with just ECDSA
    lingo = ConditionLingo(ecdsa_condition)

    # Context with only 3 variables: timestamp, signature, and discordPayload
    context = {
        ":timestamp": timestamp,
        ":discordPayload": body,
        ":signature": signature_hex,
    }
    result = lingo.eval(**context)
    assert (
        result is True
    ), "Discord Ed25519 signature should be valid using ECDSACondition with template message."

    # ===== PART 2: Expanded test - ECDSA + JSON conditions compounded =====
    # Create JSON conditions that parse the discordPayload directly from context
    # JSON condition 1: Check the message value from the command options
    json_message_condition = JsonCondition(
        data=":discordPayload",  # Parse JSON from the discordPayload context variable
        query="$.data.options[0].value",
        return_value_test=ReturnValueTest("==", "'llamas'"),
    )

    # JSON condition 2: Check the username
    json_username_condition = JsonCondition(
        data=":discordPayload",  # Same discordPayload variable
        query="$.member.user.username",
        return_value_test=ReturnValueTest("==", "'kprasch'"),
    )

    # JSON condition 3: Check the user ID
    json_userid_condition = JsonCondition(
        data=":discordPayload",
        query="$.member.user.id",
        return_value_test=ReturnValueTest("==", "'410212090289192960'"),
    )

    # JSON condition 4: Check the command name
    json_command_condition = JsonCondition(
        data=":discordPayload",
        query="$.data.name",
        return_value_test=ReturnValueTest("==", "'sign'"),
    )

    # JSON condition 5: Check the guild ID
    json_guild_condition = JsonCondition(
        data=":discordPayload",
        query="$.guild_id",
        return_value_test=ReturnValueTest("==", "'1380488052169769110'"),
    )

    # Create compound conditions combining ECDSA with JSON conditions
    # Compound 1: ECDSA AND message value check
    and_ecdsa_message_condition = AndCompoundCondition(
        operands=[ecdsa_condition, json_message_condition]
    )

    # Compound 2: ECDSA AND all user info checks
    and_ecdsa_user_info_condition = AndCompoundCondition(
        operands=[
            ecdsa_condition,
            json_username_condition,
            json_userid_condition,
        ]
    )

    # Compound 3: Complex nested condition - (ECDSA AND command) AND (username OR guild)
    complex_nested_condition = AndCompoundCondition(
        operands=[
            AndCompoundCondition(operands=[ecdsa_condition, json_command_condition]),
            OrCompoundCondition(
                operands=[json_username_condition, json_guild_condition]
            ),
        ]
    )

    # Compound 4: All conditions must be true
    all_conditions_and = AndCompoundCondition(
        operands=[
            ecdsa_condition,
            json_message_condition,
            json_username_condition,
            json_userid_condition,
            json_command_condition,
        ]
    )

    # Test all compound conditions with the same 3-variable context
    # Test 1: ECDSA AND message value
    lingo_and_message = ConditionLingo(and_ecdsa_message_condition)
    result = lingo_and_message.eval(**context)
    assert result is True, "ECDSA + message value compound condition should pass"

    # Test 2: ECDSA AND user info
    lingo_and_user = ConditionLingo(and_ecdsa_user_info_condition)
    result = lingo_and_user.eval(**context)
    assert result is True, "ECDSA + user info compound condition should pass"

    # Test 3: Complex nested condition
    lingo_complex = ConditionLingo(complex_nested_condition)
    result = lingo_complex.eval(**context)
    assert result is True, "Complex nested compound condition should pass"

    # Test 4: All conditions AND
    lingo_all = ConditionLingo(all_conditions_and)
    result = lingo_all.eval(**context)
    assert result is True, "All conditions compounded with AND should pass"

    # Test failure cases
    # Modify context to make JSON conditions fail
    wrong_context = context.copy()
    # Parse and modify the JSON payload
    wrong_body_json = json.loads(body)
    wrong_body_json["data"]["options"][0]["value"] = "alpacas"  # Wrong message
    wrong_body = json.dumps(wrong_body_json)
    wrong_context[":discordPayload"] = wrong_body

    # This should fail because message value doesn't match
    result = lingo_and_message.eval(**wrong_context)
    assert result is False, "Should fail when message value is wrong"

    # Test with invalid signature but valid JSON
    invalid_sig_context = context.copy()
    invalid_sig_context[":signature"] = "0" * len(signature_hex)  # Invalid signature

    result = lingo_and_message.eval(**invalid_sig_context)
    assert result is False, "Should fail when signature is invalid"

    # Test OR condition - should pass if at least one condition is true
    or_condition = OrCompoundCondition(
        operands=[
            ecdsa_condition,
            json_message_condition,
        ]
    )
    lingo_or = ConditionLingo(or_condition)

    # Valid signature, wrong JSON - should still pass due to OR
    mixed_context = {
        ":timestamp": timestamp,
        ":signature": signature_hex,
        ":discordPayload": wrong_body,  # Wrong message value in JSON
    }
    result = lingo_or.eval(**mixed_context)
    assert (
        result is True
    ), "OR condition should pass when at least one condition is true"

    # Both invalid - should fail
    both_invalid_context = {
        ":timestamp": timestamp,
        ":signature": "0" * len(signature_hex),  # Invalid signature
        ":discordPayload": wrong_body,  # Wrong message value in JSON
    }
    result = lingo_or.eval(**both_invalid_context)
    assert result is False, "OR condition should fail when all conditions are false"


def test_discord_json_from_body_string():
    """Test parsing Discord body JSON string directly from context variable with 3-variable context"""
    # Discord Ed25519 test vector
    public_key_hex = "b853dd9f496723daf64bf2f5a886086f790df66e61d7b6f7f98a50c9e5ede8f3"
    signature_hex = "0a12acb96843700b724f1c9dba3075a7fc482677e0c713eb6be63bfea406fb33b4715975f1062b2dff95127bd559ee23758911bd217760727dc44e7880bc6e04"
    timestamp = "1749368683"

    # This is the raw JSON string as it would come from Discord
    body = '{"app_permissions":"2248473465835073","application_id":"1380486651436073092","attachment_size_limit":10485760,"authorizing_integration_owners":{"0":"1380488052169769110"},"channel":{"flags":0,"guild_id":"1380488052169769110","icon_emoji":{"id":null,"name":"👋"},"id":"1380488052169769113","last_message_id":"1380528253168652328","name":"general","nsfw":false,"parent_id":"1380488052169769111","permissions":"2251799813685247","position":0,"rate_limit_per_user":0,"theme_color":null,"topic":null,"type":0},"channel_id":"1380488052169769113","context":0,"data":{"id":"1380515955146358918","name":"sign","options":[{"name":"message","type":3,"value":"llamas"}],"type":1},"entitlement_sku_ids":[],"entitlements":[],"guild":{"features":[],"id":"1380488052169769110","locale":"en-US"},"guild_id":"1380488052169769110","guild_locale":"en-US","id":"1381177107555680327","locale":"en-US","member":{"avatar":null,"banner":null,"communication_disabled_until":null,"deaf":false,"flags":0,"joined_at":"2025-06-06T10:06:39.888000+00:00","mute":false,"nick":null,"pending":false,"permissions":"2251799813685247","premium_since":null,"roles":[],"unusual_dm_activity_until":null,"user":{"avatar":"9c5483a989a10edc8b831b6c8f284724","avatar_decoration_data":null,"clan":null,"collectibles":null,"discriminator":"0","global_name":"kprasch","id":"410212090289192960","primary_guild":null,"public_flags":0,"username":"kprasch"}},"token":"aW50ZXJhY3Rpb246MTM4MTE3NzEwNzU1NTY4MDMyNzo2ZlVlTkdIQVFIdkdhNUN2bXlYZ1RCRkZ5YkpuVm9WUG5Bbjl0TTMyUkFTenZGYXNXclBCMjZWUWJlalczcllRak9sc0JZR3Q4WW9sODBRcDg2c2hrYmRkYzlWcjF3TjdlRFVDMVBVTkZ3Z2VmRUp4VkI1MkZGNmVvM3hkWXd1Qg","type":2,"version":1}'

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
