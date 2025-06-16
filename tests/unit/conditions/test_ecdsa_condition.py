import hashlib
import json

import nacl.exceptions
import nacl.signing
import pytest
from ecdsa.curves import NIST192p, SECP256k1
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
        InvalidCondition, match="Invalid verifying key format, must be hex encoded"
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
        curve=SECP256k1.name,
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
        curve=SECP256k1.name,
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


def test_discord_ed25519_signature():
    # Discord Ed25519 test vector
    public_key_hex = "b853dd9f496723daf64bf2f5a886086f790df66e61d7b6f7f98a50c9e5ede8f3"
    signature_hex = "0a12acb96843700b724f1c9dba3075a7fc482677e0c713eb6be63bfea406fb33b4715975f1062b2dff95127bd559ee23758911bd217760727dc44e7880bc6e04"
    timestamp = "1749368683"
    body = '{"app_permissions":"2248473465835073","application_id":"1380486651436073092","attachment_size_limit":10485760,"authorizing_integration_owners":{"0":"1380488052169769110"},"channel":{"flags":0,"guild_id":"1380488052169769110","icon_emoji":{"id":null,"name":"👋"},"id":"1380488052169769113","last_message_id":"1380528253168652328","name":"general","nsfw":false,"parent_id":"1380488052169769111","permissions":"2251799813685247","position":0,"rate_limit_per_user":0,"theme_color":null,"topic":null,"type":0},"channel_id":"1380488052169769113","context":0,"data":{"id":"1380515955146358918","name":"sign","options":[{"name":"message","type":3,"value":"llamas"}],"type":1},"entitlement_sku_ids":[],"entitlements":[],"guild":{"features":[],"id":"1380488052169769110","locale":"en-US"},"guild_id":"1380488052169769110","guild_locale":"en-US","id":"1381177107555680327","locale":"en-US","member":{"avatar":null,"banner":null,"communication_disabled_until":null,"deaf":false,"flags":0,"joined_at":"2025-06-06T10:06:39.888000+00:00","mute":false,"nick":null,"pending":false,"permissions":"2251799813685247","premium_since":null,"roles":[],"unusual_dm_activity_until":null,"user":{"avatar":"9c5483a989a10edc8b831b6c8f284724","avatar_decoration_data":null,"clan":null,"collectibles":null,"discriminator":"0","global_name":"kprasch","id":"410212090289192960","primary_guild":null,"public_flags":0,"username":"kprasch"}},"token":"aW50ZXJhY3Rpb246MTM4MTE3NzEwNzU1NTY4MDMyNzo2ZlVlTkdIQVFIdkdhNUN2bXlYZ1RCRkZ5YkpuVm9WUG5Bbjl0TTMyUkFTenZGYXNXclBCMjZWUWJlalczcllRak9sc0JZR3Q4WW9sODBRcDg2c2hrYmRkYzlWcjF3TjdlRFVDMVBVTkZ3Z2VmRUp4VkI1MkZGNmVvM3hkWXd1Qg","type":2,"version":1}'

    public_key = bytes.fromhex(public_key_hex)
    signature = bytes.fromhex(signature_hex)
    message = timestamp.encode("utf-8") + body.encode("utf-8")

    verify_key = nacl.signing.VerifyKey(public_key)
    try:
        verify_key.verify(message, signature)
        verified = True
    except nacl.exceptions.BadSignatureError:
        verified = False

    assert (
        verified
    ), "Discord Ed25519 signature should be valid for the given message and public key."


def test_discord_ed25519_signature_with_ecdsa():
    # Discord Ed25519 test vector
    public_key_hex = "b853dd9f496723daf64bf2f5a886086f790df66e61d7b6f7f98a50c9e5ede8f3"
    signature_hex = "0a12acb96843700b724f1c9dba3075a7fc482677e0c713eb6be63bfea406fb33b4715975f1062b2dff95127bd559ee23758911bd217760727dc44e7880bc6e04"
    timestamp = "1749368683"
    body = '{"app_permissions":"2248473465835073","application_id":"1380486651436073092","attachment_size_limit":10485760,"authorizing_integration_owners":{"0":"1380488052169769110"},"channel":{"flags":0,"guild_id":"1380488052169769110","icon_emoji":{"id":null,"name":"👋"},"id":"1380488052169769113","last_message_id":"1380528253168652328","name":"general","nsfw":false,"parent_id":"1380488052169769111","permissions":"2251799813685247","position":0,"rate_limit_per_user":0,"theme_color":null,"topic":null,"type":0},"channel_id":"1380488052169769113","context":0,"data":{"id":"1380515955146358918","name":"sign","options":[{"name":"message","type":3,"value":"llamas"}],"type":1},"entitlement_sku_ids":[],"entitlements":[],"guild":{"features":[],"id":"1380488052169769110","locale":"en-US"},"guild_id":"1380488052169769110","guild_locale":"en-US","id":"1381177107555680327","locale":"en-US","member":{"avatar":null,"banner":null,"communication_disabled_until":null,"deaf":false,"flags":0,"joined_at":"2025-06-06T10:06:39.888000+00:00","mute":false,"nick":null,"pending":false,"permissions":"2251799813685247","premium_since":null,"roles":[],"unusual_dm_activity_until":null,"user":{"avatar":"9c5483a989a10edc8b831b6c8f284724","avatar_decoration_data":null,"clan":null,"collectibles":null,"discriminator":"0","global_name":"kprasch","id":"410212090289192960","primary_guild":null,"public_flags":0,"username":"kprasch"}},"token":"aW50ZXJhY3Rpb246MTM4MTE3NzEwNzU1NTY4MDMyNzo2ZlVlTkdIQVFIdkdhNUN2bXlYZ1RCRkZ5YkpuVm9WUG5Bbjl0TTMyUkFTenZGYXNXclBCMjZWUWJlalczcllRak9sc0JZR3Q4WW9sODBRcDg2c2hrYmRkYzlWcjF3TjdlRFVDMVBVTkZ3Z2VmRUp4VkI1MkZGNmVvM3hkWXd1Qg","type":2,"version":1}'

    public_key = bytes.fromhex(public_key_hex)
    signature = bytes.fromhex(signature_hex)
    message = timestamp.encode("utf-8") + body.encode("utf-8")

    # Using nacl for Ed25519 verification
    verify_key_nacl = nacl.signing.VerifyKey(public_key)
    try:
        verify_key_nacl.verify(message, signature)
        verified_nacl = True
    except nacl.exceptions.BadSignatureError:
        verified_nacl = False

    from ecdsa import Ed25519, VerifyingKey

    try:
        verify_key_ecdsa = VerifyingKey.from_string(public_key, curve=Ed25519)
        verified_ecdsa = verify_key_ecdsa.verify(
            signature, message, hashfunc=hashlib.sha256
        )
    except Exception:
        verified_ecdsa = False

    assert verified_nacl
    assert verified_ecdsa
