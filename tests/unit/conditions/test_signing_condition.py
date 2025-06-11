import json

import pytest

from nucypher.policy.conditions.exceptions import (
    InvalidCondition,
    InvalidContextVariableData,
    RequiredContextVariable,
)
from nucypher.policy.conditions.lingo import (
    ConditionLingo,
    ConditionType,
    ReturnValueTest,
)
from nucypher.policy.conditions.signing.base import (
    SIGNING_CONDITION_OBJECT_CONTEXT_VAR,
    SigningObjectAttributeCondition,
)
from nucypher.policy.conditions.utils import ConditionProviderManager


@pytest.fixture
def condition_provider_manager():
    """Fixture to provide a mock ConditionProviderManager."""
    return ConditionProviderManager({})


def test_invalid_signing_object_attribute_condition():
    # invalid condition type
    with pytest.raises(InvalidCondition, match=ConditionType.ATTRIBUTE.value):
        _ = SigningObjectAttributeCondition(
            condition_type=ConditionType.TIME.value,
            attribute_name="some_attribute",
            return_value_test=ReturnValueTest("==", 0),
        )

    # no attribute name
    with pytest.raises(InvalidCondition, match="Missing data for required field"):
        _ = SigningObjectAttributeCondition(
            attribute_name=None,
            return_value_test=ReturnValueTest("==", 0),
        )


def test_signing_object_attribute_condition_initialization():
    condition = SigningObjectAttributeCondition(
        condition_type=ConditionType.ATTRIBUTE.value,
        attribute_name="call_data",
        return_value_test=ReturnValueTest("==", 0),
    )

    assert condition.condition_type == ConditionType.ATTRIBUTE.value
    assert condition.signing_object_context_var == SIGNING_CONDITION_OBJECT_CONTEXT_VAR
    assert condition.attribute_name == "call_data"
    assert condition.return_value_test.eval(0)


def test_signing_object_attribute_condition_verify_no_object_provided_in_context(
    condition_provider_manager,
):
    condition = SigningObjectAttributeCondition(
        attribute_name="call_data",
        return_value_test=ReturnValueTest("==", "0x1234567890abcdef"),
    )

    context = {}
    with pytest.raises(
        RequiredContextVariable,
        match="No value provided for unrecognized context variable",
    ):
        _ = condition.verify(providers=condition_provider_manager, **context)

    context = {SIGNING_CONDITION_OBJECT_CONTEXT_VAR: None}
    with pytest.raises(RequiredContextVariable):
        _ = condition.verify(providers=condition_provider_manager, **context)


def test_signing_object_attribute_condition_verify_invalid_attribute_name_for_object(
    condition_provider_manager,
):
    condition = SigningObjectAttributeCondition(
        attribute_name="call_data",
        return_value_test=ReturnValueTest("==", "0x1234567890abcdef"),
    )

    signing_object = "object is just a string"  # string has not attribute 'call_data'
    context = {SIGNING_CONDITION_OBJECT_CONTEXT_VAR: signing_object}

    with pytest.raises(InvalidContextVariableData, match="does not have attribute"):
        _ = condition.verify(providers=condition_provider_manager, **context)


def test_signing_object_attribute_condition_verify_hex_string(
    mocker, condition_provider_manager
):
    signing_object = mocker.Mock()
    signing_object.call_data = "0x1234567890abcdef"
    condition = SigningObjectAttributeCondition(
        attribute_name="call_data",
        return_value_test=ReturnValueTest("==", "0x1234567890abcdef"),
    )
    context = {SIGNING_CONDITION_OBJECT_CONTEXT_VAR: signing_object}

    success, result = condition.verify(providers=condition_provider_manager, **context)
    assert success is True
    assert result == signing_object.call_data

    # failure case
    signing_object.call_data = "0xdeadbeef"
    success, result = condition.verify(providers=condition_provider_manager, **context)
    assert success is False
    assert result == signing_object.call_data


def test_signing_object_attribute_condition_verify_allowed_string_list(
    mocker, condition_provider_manager
):
    signing_object = mocker.Mock()
    signing_object.method_name = "burn"

    allowed_method_calls = ['"transfer"', '"approve"', '"mint"', '"burn"']
    condition = SigningObjectAttributeCondition(
        attribute_name="method_name",
        return_value_test=ReturnValueTest("in", allowed_method_calls),
    )
    context = {SIGNING_CONDITION_OBJECT_CONTEXT_VAR: signing_object}

    success, result = condition.verify(providers=condition_provider_manager, **context)
    assert success is True
    assert result == signing_object.method_name

    # failure case with disallowed method name
    signing_object.method_name = "transferFrom"
    success, result = condition.verify(providers=condition_provider_manager, **context)
    assert success is False
    assert result == signing_object.method_name


def test_signing_object_attribute_condition_verify_number_value(
    mocker, condition_provider_manager
):
    signing_object = mocker.Mock()
    signing_object.gas_limit = 10_000_000

    condition = SigningObjectAttributeCondition(
        attribute_name="gas_limit",
        return_value_test=ReturnValueTest(">", 9_000_000),
    )
    context = {SIGNING_CONDITION_OBJECT_CONTEXT_VAR: signing_object}

    success, result = condition.verify(providers=condition_provider_manager, **context)
    assert success is True
    assert result == signing_object.gas_limit

    # failure case with disallowed method name
    signing_object.gas_limit = 5_000
    success, result = condition.verify(providers=condition_provider_manager, **context)
    assert success is False
    assert result == signing_object.gas_limit


def test_signing_object_attribute_condition_lingo_json_serialization(
    mocker, condition_provider_manager
):
    """Test serializing and deserializing a condition lingo with ECDSA condition"""
    condition = SigningObjectAttributeCondition(
        condition_type=ConditionType.ATTRIBUTE.value,
        attribute_name="call_data",
        return_value_test=ReturnValueTest("==", "0x1234567890abcdef"),
    )

    signing_object = mocker.Mock()
    signing_object.call_data = "0x1234567890abcdef"
    context = {SIGNING_CONDITION_OBJECT_CONTEXT_VAR: signing_object}

    success, result = condition.verify(providers=condition_provider_manager, **context)
    assert success is True
    assert result == signing_object.call_data

    # Create condition lingo
    lingo = ConditionLingo(condition)

    # Convert lingo to JSON
    original_lingo_json = lingo.to_json()

    # Parse JSON to dict and verify structure
    lingo_dict = json.loads(original_lingo_json)
    assert lingo_dict["version"] == ConditionLingo.VERSION
    assert lingo_dict["condition"]["conditionType"] == ConditionType.ATTRIBUTE.value

    # Recreate lingo from JSON
    recreated_lingo = ConditionLingo.from_json(original_lingo_json)
    assert recreated_lingo.to_json() == original_lingo_json

    # works the same
    signing_object = mocker.Mock()
    signing_object.call_data = "0x1234567890abcdef"

    success, result = recreated_lingo.condition.verify(
        providers=condition_provider_manager, **context
    )
    assert success is True
    assert result == signing_object.call_data
