import pytest
from eth_account import Account

from nucypher.policy.conditions.address import AddressAllowlistCondition
from nucypher.policy.conditions.exceptions import (
    InvalidCondition,
    InvalidConditionContext,
    InvalidConditionLingo,
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


def test_address_allowlist_condition_schema_validation():
    """Test the schema validation of AddressAllowlistCondition."""
    # Create test accounts
    account1 = Account.create()
    account2 = Account.create()
    addresses = [account1.address, account2.address]
    
    # Create condition
    condition = AddressAllowlistCondition(addresses=addresses)
    condition_dict = condition.to_dict()

    # No issues here
    AddressAllowlistCondition.from_dict(condition_dict)

    # No issues with optional name
    condition_dict["name"] = "my_address_allowlist"
    AddressAllowlistCondition.from_dict(condition_dict)

    with pytest.raises(InvalidConditionLingo):
        # No conditionType
        condition_dict = condition.to_dict()
        del condition_dict["conditionType"]
        AddressAllowlistCondition.from_dict(condition_dict)

    with pytest.raises(InvalidConditionLingo):
        # No addresses defined
        condition_dict = condition.to_dict()
        del condition_dict["addresses"]
        AddressAllowlistCondition.from_dict(condition_dict)

    with pytest.raises(InvalidConditionLingo):
        # Invalid condition type
        condition_dict = condition.to_dict()
        condition_dict["conditionType"] = "invalid-condition-type"
        AddressAllowlistCondition.from_dict(condition_dict)

    with pytest.raises(InvalidConditionLingo):
        # Empty addresses list
        condition_dict = condition.to_dict()
        condition_dict["addresses"] = []
        AddressAllowlistCondition.from_dict(condition_dict)

    with pytest.raises(InvalidConditionLingo):
        # Invalid address format
        condition_dict = condition.to_dict()
        condition_dict["addresses"] = ["not-an-ethereum-address"]
        AddressAllowlistCondition.from_dict(condition_dict)
