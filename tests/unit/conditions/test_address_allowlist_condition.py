import pytest
from eth_account import Account
from eth_account.messages import encode_defunct, encode_typed_data
from hexbytes import HexBytes

from nucypher.policy.conditions.address import AddressAllowlistCondition
from nucypher.policy.conditions.exceptions import (
    InvalidCondition,
    InvalidConditionContext,
    InvalidConditionLingo,
)
from nucypher.policy.conditions.context import USER_ADDRESS_CONTEXT
from nucypher.policy.conditions.auth.evm import EvmAuth


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

    # Create proper EIP712 typed data structures for each account
    def create_auth_message_for_account(account):
        # Create a proper EIP712 typed data structure
        typed_data = {
            "primaryType": "Wallet",
            "types": {
                "EIP712Domain": [
                    {"name": "name", "type": "string"},
                    {"name": "version", "type": "string"},
                    {"name": "chainId", "type": "uint256"},
                    {"name": "salt", "type": "bytes32"},
                ],
                "Wallet": [
                    {"name": "address", "type": "string"},
                    {"name": "blockNumber", "type": "uint256"},
                    {"name": "blockHash", "type": "bytes32"},
                    {"name": "signatureText", "type": "string"},
                ],
            },
            "domain": {
                "name": "TestDomain",
                "version": "1",
                "chainId": 1,
                "salt": "0x3e6365d35fd4e53cbc00b080b0742b88f8b735352ea54c0534ed6a2e44a83ff0",
            },
            "message": {
                "address": account.address,
                "blockNumber": 12345678,
                "blockHash": "0x104dfae58be4a9b15d59ce447a565302d5658914f1093f10290cd846fbe258b7",
                "signatureText": f"I'm the owner of address {account.address}",
            },
        }

        # Sign the typed data
        signable_message = encode_typed_data(full_message=typed_data)
        signature = account.sign_message(signable_message=signable_message)

        # Return the auth message structure
        return {
            "signature": signature.signature.hex(),
            "address": account.address,
            "scheme": EvmAuth.AuthScheme.EIP712.value,
            "typedData": typed_data,
        }

    # Create auth messages for each account
    auth_message1 = create_auth_message_for_account(allowed_account1)
    auth_message2 = create_auth_message_for_account(allowed_account2)
    auth_message_not_allowed = create_auth_message_for_account(not_allowed_account)

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
