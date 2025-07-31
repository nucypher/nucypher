from ecdsa import Ed25519, SECP256k1, SigningKey
from ecdsa.util import sigencode_string
from hexbytes import HexBytes

from nucypher.policy.conditions.ecdsa import ECDSACondition, ECDSAVerificationCall
from nucypher.policy.conditions.lingo import (
    CompoundCondition,
    ConditionLingo,
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

    # Construct the message to be signed
    message = timestamp.encode("utf-8") + body.encode("utf-8")

    # Create ECDSACondition using the Discord public key and signature
    ecdsa_condition = ECDSACondition(
        message=":message",
        signature=":signature",
        verifying_key=public_key_hex,
        curve=Ed25519.name,
    )

    # Create condition lingo
    lingo = ConditionLingo(ecdsa_condition)

    # Valid context
    context = {":message": HexBytes(message).hex(), ":signature": signature_hex}
    result = lingo.eval(**context)
    assert (
        result is True
    ), "Discord Ed25519 signature should be valid using ECDSACondition."
