import pytest
from eth_account import Account

from nucypher.policy.conditions.address import AddressAllowlistCondition
from nucypher.policy.conditions.exceptions import (
    InvalidCondition,
    InvalidConditionContext,
)
from nucypher.policy.conditions.context import USER_ADDRESS_CONTEXT


def test_address_allowlist_condition_init():
    """Test the initialization of AddressAllowlistCondition."""
    # Create test addresses
    account1 = Account.create()
    account2 = Account.create()

    addresses = [account1.address, account2.address]

    # Test successful initialization
    condition = AddressAllowlistCondition(addresses=addresses)
    assert condition.condition_type == "address-allowlist"
    assert set(condition.addresses) == set(addresses)

    # Test with empty addresses list
    with pytest.raises(InvalidCondition):
        AddressAllowlistCondition(addresses=[])

    # Test with invalid address
    with pytest.raises(InvalidCondition):
        AddressAllowlistCondition(addresses=["not-an-ethereum-address"])

    # Test with duplicate addresses
    with pytest.raises(InvalidCondition):
        AddressAllowlistCondition(addresses=[account1.address, account1.address])


def test_address_allowlist_condition_verify():
    """Test the verification of AddressAllowlistCondition."""
    # Create test accounts
    allowed_account1 = Account.create()
    allowed_account2 = Account.create()
    not_allowed_account = Account.create()

    # Create condition with allowed accounts
    addresses = [allowed_account1.address, allowed_account2.address]
    condition = AddressAllowlistCondition(addresses=addresses)

    # Test successful verification with allowed account
    context = {USER_ADDRESS_CONTEXT: {"address": allowed_account1.address}}

    result, _ = condition.verify(**context)
    assert result is True

    # Test verification with not allowed account
    context = {USER_ADDRESS_CONTEXT: {"address": not_allowed_account.address}}

    result, _ = condition.verify(**context)
    assert result is False

    # Test with another allowed account
    context = {USER_ADDRESS_CONTEXT: {"address": allowed_account2.address}}

    result, _ = condition.verify(**context)
    assert result is True

    # Test verification with missing context
    with pytest.raises(InvalidConditionContext):
        condition.verify()

    result, _ = condition.verify(**context)
    assert result is True


def test_address_allowlist_condition_serialization():
    """Test the serialization and deserialization of AddressAllowlistCondition."""
    # Create test accounts
    account1 = Account.create()
    account2 = Account.create()

    # Create condition
    addresses = [account1.address, account2.address]
    original_condition = AddressAllowlistCondition(
        addresses=addresses, name="Test Condition"
    )

    # Serialize to dict
    condition_dict = original_condition.to_dict()

    # Check dict structure
    assert condition_dict["conditionType"] == "address-allowlist"
    assert set(condition_dict["addresses"]) == set(addresses)
    assert condition_dict["name"] == "Test Condition"

    # Deserialize from dict
    deserialized_condition = AddressAllowlistCondition.from_dict(condition_dict)

    # Check equality
    assert original_condition == deserialized_condition

    # Serialize to JSON
    json_str = original_condition.to_json()

    # Deserialize from JSON
    deserialized_condition = AddressAllowlistCondition.from_json(json_str)

    # Check equality
    assert original_condition == deserialized_condition
