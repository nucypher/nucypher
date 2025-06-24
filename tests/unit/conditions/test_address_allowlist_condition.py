import pytest
from eth_account import Account

from nucypher.policy.conditions.address import AddressAllowlistCondition
from nucypher.policy.conditions.context import USER_ADDRESS_CONTEXT
from nucypher.policy.conditions.exceptions import (
    InvalidCondition,
    InvalidConditionContext,
    InvalidConditionLingo,
)
from nucypher.policy.conditions.lingo import ConditionType


def test_address_allowlist_condition_init():
    """Test the initialization of AddressAllowlistCondition."""
    # Create test addresses
    account1 = Account.create()
    account2 = Account.create()

    addresses = [account1.address, account2.address]

    # Test successful initialization
    condition = AddressAllowlistCondition(
        user_address=USER_ADDRESS_CONTEXT, addresses=addresses
    )
    assert condition.condition_type == ConditionType.ADDRESS_ALLOWLIST.value
    assert set(condition.addresses) == set(addresses)

    # Test with empty addresses list
    with pytest.raises(InvalidCondition):
        AddressAllowlistCondition(user_address=USER_ADDRESS_CONTEXT, addresses=[])

    # Test with invalid address
    with pytest.raises(InvalidCondition):
        AddressAllowlistCondition(
            user_address=USER_ADDRESS_CONTEXT,
            addresses=["not-an-ethereum-address"],
        )

    # Test with duplicate addresses
    with pytest.raises(InvalidCondition):
        AddressAllowlistCondition(
            user_address=USER_ADDRESS_CONTEXT,
            addresses=[account1.address, account1.address],
        )

    # Test with invalid user_address value (not the correct context variable)
    with pytest.raises(InvalidCondition, match="Must be equal to :userAddress"):
        AddressAllowlistCondition(
            user_address="invalid_context_variable",
            addresses=[account1.address],
        )

    # Test with non-checksummed address in addresses
    # Use a static address with known invalid checksum (should be 0xAb5801a7D398351b8bE11C439e05C5B3259aeC9B)
    non_checksummed_address = "0xAb5801a7D398351b8bE11C439e05C5B3259aec9b"
    with pytest.raises(InvalidCondition, match="not a checksummed address"):
        AddressAllowlistCondition(
            user_address=USER_ADDRESS_CONTEXT,
            addresses=[non_checksummed_address],
        )


def test_address_allowlist_condition_verify(valid_eip4361_auth_message_factory):
    """Test the verification of AddressAllowlistCondition."""
    # Create test accounts

    auth_message1 = valid_eip4361_auth_message_factory()
    allowed_account1 = auth_message1["address"]

    auth_message2 = valid_eip4361_auth_message_factory()
    allowed_account2 = auth_message2["address"]

    auth_message_not_allowed = valid_eip4361_auth_message_factory()

    # Create condition with allowed accounts
    addresses = [allowed_account1, allowed_account2]
    condition = AddressAllowlistCondition(
        user_address=USER_ADDRESS_CONTEXT,
        addresses=addresses,
    )

    # Test successful verification with allowed account
    context = {USER_ADDRESS_CONTEXT: auth_message1}
    result, _ = condition.verify(**context)
    assert result is True

    # Test verification with not allowed account
    context = {USER_ADDRESS_CONTEXT: auth_message_not_allowed}
    result, _ = condition.verify(**context)
    assert result is False

    # Test with another allowed account
    context = {USER_ADDRESS_CONTEXT: auth_message2}
    result, _ = condition.verify(**context)
    assert result is True

    # Test verification with missing context
    with pytest.raises(InvalidConditionContext):
        condition.verify()


def test_address_allowlist_condition_schema_validation():
    """Test the schema validation of AddressAllowlistCondition."""
    # Create test accounts
    account1 = Account.create()
    account2 = Account.create()
    addresses = [account1.address, account2.address]

    # Create condition
    condition = AddressAllowlistCondition(
        user_address=USER_ADDRESS_CONTEXT, addresses=addresses
    )
    condition_dict = condition.to_dict()

    # No issues here
    AddressAllowlistCondition.from_dict(condition_dict)

    # No issues with optional name
    condition_dict["name"] = "my_address_allowlist"
    AddressAllowlistCondition.from_dict(condition_dict)

    with pytest.raises(InvalidConditionLingo, match="Missing data for required field"):
        # No conditionType
        condition_dict = condition.to_dict()
        del condition_dict["conditionType"]
        AddressAllowlistCondition.from_dict(condition_dict)

    with pytest.raises(InvalidConditionLingo, match="Missing data for required field"):
        # No addresses defined
        condition_dict = condition.to_dict()
        del condition_dict["addresses"]
        AddressAllowlistCondition.from_dict(condition_dict)

    with pytest.raises(
        InvalidConditionLingo, match="Must be equal to address-allowlist"
    ):
        # Invalid condition type
        condition_dict = condition.to_dict()
        condition_dict["conditionType"] = "invalid-condition-type"
        AddressAllowlistCondition.from_dict(condition_dict)

    with pytest.raises(InvalidConditionLingo, match="Length must be between 1 and 25"):
        # Empty addresses list
        condition_dict = condition.to_dict()
        condition_dict["addresses"] = []
        AddressAllowlistCondition.from_dict(condition_dict)

    with pytest.raises(InvalidConditionLingo, match="Invalid Ethereum address"):
        # Invalid address format
        condition_dict = condition.to_dict()
        condition_dict["addresses"] = ["not-an-ethereum-address"]
        AddressAllowlistCondition.from_dict(condition_dict)

    with pytest.raises(InvalidConditionLingo, match="Missing data for required field"):
        # Missing user_address field
        condition_dict = condition.to_dict()
        del condition_dict["userAddress"]
        AddressAllowlistCondition.from_dict(condition_dict)

    with pytest.raises(InvalidConditionLingo, match="Must be equal to :userAddress"):
        # Invalid user_address value
        condition_dict = condition.to_dict()
        condition_dict["userAddress"] = "wrong-value"
        AddressAllowlistCondition.from_dict(condition_dict)
