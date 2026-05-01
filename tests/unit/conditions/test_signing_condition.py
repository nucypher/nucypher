import copy
import json
import random

import pytest
from ecdsa import SECP256k1, SigningKey
from ecdsa.util import sigencode_string
from hexbytes import HexBytes
from nucypher_core import UserOperation
from web3 import Web3

from nucypher.policy.conditions.ecdsa import ECDSACondition, ECDSAVerificationCall
from nucypher.policy.conditions.exceptions import (
    InvalidCondition,
    InvalidContextVariableData,
    RequiredContextVariable,
)
from nucypher.policy.conditions.json.api import JsonApiCondition
from nucypher.policy.conditions.json.auth import AuthorizationType
from nucypher.policy.conditions.lingo import (
    ConditionLingo,
    ConditionType,
    ConditionVariable,
    ReturnValueTest,
    SequentialCondition,
    VariableOperation,
)
from nucypher.policy.conditions.signing.base import (
    SIGNING_CONDITION_OBJECT_CONTEXT_VAR,
    AbiCallValidation,
    AbiParameterValidation,
    SigningObjectAbiAttributeCondition,
    SigningObjectAttributeCondition,
)
from nucypher.policy.conditions.utils import ConditionProviderManager
from nucypher.utilities.abi import encode_human_readable_call
from tests.utils.erc4337 import (
    create_erc20_approve,
    create_erc20_transfer,
    create_eth_transfer,
    encode_function_call,
)


@pytest.fixture
def condition_provider_manager():
    """Fixture to provide a mock ConditionProviderManager."""
    return ConditionProviderManager({})


def test_invalid_signing_object_attribute_condition():
    # invalid condition type
    with pytest.raises(InvalidCondition, match=ConditionType.SIGNING_ATTRIBUTE.value):
        _ = SigningObjectAttributeCondition(
            condition_type=ConditionType.TIME.value,
            attribute_name="some_attribute",
            return_value_test=ReturnValueTest("==", 0),
        )

    # no attribute name
    with pytest.raises(InvalidCondition, match="Field may not be null"):
        _ = SigningObjectAttributeCondition(
            attribute_name=None,
            return_value_test=ReturnValueTest("==", 0),
        )


def test_signing_object_attribute_condition_initialization():
    condition = SigningObjectAttributeCondition(
        condition_type=ConditionType.SIGNING_ATTRIBUTE.value,
        attribute_name="call_data",
        return_value_test=ReturnValueTest("==", 0),
    )

    assert condition.condition_type == ConditionType.SIGNING_ATTRIBUTE.value
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

    allowed, result = condition.verify(providers=condition_provider_manager, **context)
    assert allowed is True
    assert result == signing_object.call_data

    # failure case
    signing_object.call_data = "0xdeadbeef"
    allowed, result = condition.verify(providers=condition_provider_manager, **context)
    assert allowed is False
    assert result == signing_object.call_data


def test_signing_object_attribute_condition_verify_allowed_string_list(
    mocker, condition_provider_manager
):
    signing_object = mocker.Mock()
    signing_object.data = "burn"

    allowed_data_values = ['"feel"', '"the"', '"burn"']
    condition = SigningObjectAttributeCondition(
        attribute_name="data",
        return_value_test=ReturnValueTest("in", allowed_data_values),
    )
    context = {SIGNING_CONDITION_OBJECT_CONTEXT_VAR: signing_object}

    allowed, result = condition.verify(providers=condition_provider_manager, **context)
    assert allowed is True
    assert result == signing_object.data

    # failure case with disallowed value
    signing_object.data = "fire"
    allowed, result = condition.verify(providers=condition_provider_manager, **context)
    assert allowed is False
    assert result == signing_object.data


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

    allowed, result = condition.verify(providers=condition_provider_manager, **context)
    assert allowed is True
    assert result == signing_object.gas_limit

    # failure case with disallowed method name
    signing_object.gas_limit = 5_000
    allowed, result = condition.verify(providers=condition_provider_manager, **context)
    assert allowed is False
    assert result == signing_object.gas_limit


def test_signing_object_attribute_condition_verify_userop_sender(
    condition_provider_manager, get_random_checksum_address
):
    sender = get_random_checksum_address()
    user_op = create_eth_transfer(
        sender=sender, nonce=0, to=get_random_checksum_address(), value=10_000_000
    )

    condition = SigningObjectAttributeCondition(
        attribute_name="sender",
        return_value_test=ReturnValueTest("==", sender),
    )
    context = {SIGNING_CONDITION_OBJECT_CONTEXT_VAR: user_op}
    success, _ = condition.verify(providers=condition_provider_manager, **context)
    assert success is True

    invalid_sender_user_op = create_eth_transfer(
        sender=get_random_checksum_address(),
        nonce=0,
        to=get_random_checksum_address(),
        value=10_000_000,
    )
    context = {SIGNING_CONDITION_OBJECT_CONTEXT_VAR: invalid_sender_user_op}
    success, _ = condition.verify(providers=condition_provider_manager, **context)
    assert success is False


def test_signing_object_attribute_condition_lingo_json_serialization(
    mocker, condition_provider_manager
):
    """Test serializing and deserializing a condition lingo with ECDSA condition"""
    condition = SigningObjectAttributeCondition(
        condition_type=ConditionType.SIGNING_ATTRIBUTE.value,
        attribute_name="call_data",
        return_value_test=ReturnValueTest("==", "0x1234567890abcdef"),
    )

    signing_object = mocker.Mock()
    signing_object.call_data = "0x1234567890abcdef"
    context = {SIGNING_CONDITION_OBJECT_CONTEXT_VAR: signing_object}

    allowed, result = condition.verify(providers=condition_provider_manager, **context)
    assert allowed is True
    assert result == signing_object.call_data

    # Create condition lingo
    lingo = ConditionLingo(condition)

    # Convert lingo to JSON
    original_lingo_json = lingo.to_json()

    # Parse JSON to dict and verify structure
    lingo_dict = json.loads(original_lingo_json)
    assert lingo_dict["version"] == ConditionLingo.VERSION
    assert (
        lingo_dict["condition"]["conditionType"]
        == ConditionType.SIGNING_ATTRIBUTE.value
    )

    # Recreate lingo from JSON
    recreated_lingo = ConditionLingo.from_json(original_lingo_json)
    assert recreated_lingo.to_json() == original_lingo_json

    # works the same
    signing_object = mocker.Mock()
    signing_object.call_data = "0x1234567890abcdef"

    allowed, result = recreated_lingo.condition.verify(
        providers=condition_provider_manager, **context
    )
    assert allowed is True
    assert result == signing_object.call_data


def test_invalid_signing_object_abi_attribute_condition():
    # invalid condition type
    with pytest.raises(
        InvalidCondition, match=ConditionType.SIGNING_ABI_ATTRIBUTE.value
    ):
        _ = SigningObjectAbiAttributeCondition(
            condition_type=ConditionType.TIME.value,
            attribute_name="call_data",
            abi_validation=AbiCallValidation({"transfer(address,uint256)": []}),
        )

    # no allowed abi calls
    with pytest.raises(InvalidCondition, match="Field may not be null"):
        _ = SigningObjectAbiAttributeCondition(
            attribute_name="call_data", abi_validation=None
        )

    with pytest.raises(ValueError, match="At least one allowed abi call"):
        _ = SigningObjectAbiAttributeCondition(
            attribute_name="call_data",
            abi_validation=AbiCallValidation({}),
        )

    # invalid abi decode string
    with pytest.raises(ValueError, match="Invalid ABI signature"):
        _ = SigningObjectAbiAttributeCondition(
            attribute_name="call_data",
            abi_validation=AbiCallValidation(
                {"transfer(address,uint257)": []}  # invalid data type in signature
            ),
        )

    # no abi index value
    with pytest.raises(ValueError, match="Field may not be null"):
        _ = SigningObjectAbiAttributeCondition(
            attribute_name="call_data",
            abi_validation=AbiCallValidation(
                {
                    "transfer(address,uint256)": [
                        AbiParameterValidation(
                            parameter_index=None,
                            return_value_test=ReturnValueTest("==", 0),
                        )
                    ]
                }
            ),
        )

    # negative abi index
    with pytest.raises(ValueError, match="Must be greater than or equal to 0"):
        _ = SigningObjectAbiAttributeCondition(
            attribute_name="call_data",
            abi_validation=AbiCallValidation(
                {
                    "transfer(address,uint256)": [
                        AbiParameterValidation(
                            parameter_index=-1,
                            return_value_test=ReturnValueTest("==", 0),
                        )
                    ]
                }
            ),
        )

    # abi index out of range
    with pytest.raises(ValueError, match="Parameter value index '2' is out of range"):
        _ = SigningObjectAbiAttributeCondition(
            attribute_name="call_data",
            abi_validation=AbiCallValidation(
                {
                    "transfer(address,uint256)": [
                        AbiParameterValidation(
                            parameter_index=2,
                            return_value_test=ReturnValueTest("==", 0),
                        )
                    ]
                }
            ),
        )

    # invalid sub_indices on non-indexable type
    with pytest.raises(ValueError, match="not indexable"):
        _ = SigningObjectAbiAttributeCondition(
            attribute_name="call_data",
            abi_validation=AbiCallValidation(
                {
                    "execute(address,uint256,bytes)": [
                        AbiParameterValidation(
                            parameter_index=0,
                            sub_indices=[0],  # address is not indexable
                            return_value_test=ReturnValueTest("==", 0),
                        )
                    ]
                }
            ),
        )

    # tuple index out of range
    with pytest.raises(ValueError, match="out of range"):
        _ = SigningObjectAbiAttributeCondition(
            attribute_name="call_data",
            abi_validation=AbiCallValidation(
                {
                    "execute((address,uint256,bytes))": [
                        AbiParameterValidation(
                            parameter_index=0,
                            sub_indices=[3],  # tuple only has 3 fields (0, 1, 2)
                            return_value_test=ReturnValueTest("==", 0),
                        )
                    ]
                }
            ),
        )

    # both return value test and nested_validation provided which isn't allowed
    with pytest.raises(ValueError, match="return value test or nested abi validation"):
        _ = SigningObjectAbiAttributeCondition(
            attribute_name="call_data",
            abi_validation=AbiCallValidation(
                {
                    "execute(address,uint256,bytes)": [
                        AbiParameterValidation(
                            parameter_index=2,
                            return_value_test=ReturnValueTest("==", 0),
                            nested_abi_validation=AbiCallValidation(
                                {"transfer(address,uint256)": []}
                            ),
                        )
                    ]
                }
            ),
        )

    # nested ABI validation for non-bytes type
    with pytest.raises(
        ValueError, match="Nested ABI validation is only supported for bytes type"
    ):
        _ = SigningObjectAbiAttributeCondition(
            attribute_name="callData",
            abi_validation=AbiCallValidation(
                {
                    "execute(address,uint256,bytes)": [
                        AbiParameterValidation(
                            parameter_index=0,  # incorrect index for bytes
                            nested_abi_validation=AbiCallValidation(
                                {
                                    "transfer(address,uint256)": [],
                                }
                            ),
                        )
                    ],
                }
            ),
        )

    # nested ABI validation for non-bytes type within tuple
    with pytest.raises(
        ValueError, match="Nested ABI validation is only supported for bytes type"
    ):
        _ = SigningObjectAbiAttributeCondition(
            attribute_name="callData",
            abi_validation=AbiCallValidation(
                {
                    "execute((address,uint256,bytes))": [
                        AbiParameterValidation(
                            parameter_index=0,  # correct for tuple
                            sub_indices=[
                                0
                            ],  # incorrect index within tuple (address, not bytes)
                            nested_abi_validation=AbiCallValidation(
                                {
                                    "transfer(address,uint256)": [],
                                }
                            ),
                        )
                    ],
                }
            ),
        )


def test_abi_parameter_validation_sub_indices_errors():
    """Test error handling for invalid sub_indices."""
    # Using sub_indices on non-indexable type should fail at schema validation
    with pytest.raises(ValueError, match="not indexable"):
        _ = SigningObjectAbiAttributeCondition(
            attribute_name="call_data",
            abi_validation=AbiCallValidation(
                {
                    "transfer(address,uint256)": [
                        AbiParameterValidation(
                            parameter_index=0,
                            sub_indices=[0],  # ERROR: address is not indexable
                            return_value_test=ReturnValueTest("==", ":userAddress"),
                        )
                    ]
                }
            ),
        )

    # Using sub_indices with out-of-range tuple index should fail
    with pytest.raises(ValueError, match="out of range"):
        _ = SigningObjectAbiAttributeCondition(
            attribute_name="call_data",
            abi_validation=AbiCallValidation(
                {
                    "execute((address,uint256,bytes))": [
                        AbiParameterValidation(
                            parameter_index=0,
                            sub_indices=[5],  # ERROR: tuple only has 3 fields
                            return_value_test=ReturnValueTest("==", ":userAddress"),
                        )
                    ]
                }
            ),
        )


def test_abi_parameter_validation_array_indexing(
    condition_provider_manager, get_random_checksum_address
):
    """Test sub_indices for simple array types."""

    # Create test data with an array of addresses
    recipient1 = get_random_checksum_address()
    recipient2 = get_random_checksum_address()

    # Encode a batchTransfer call with array parameters
    call_data = encode_human_readable_call(
        "batchTransfer(address[],uint256[])",
        [[recipient1, recipient2], [1000, 2000]],
    )

    user_op = UserOperation(
        sender=get_random_checksum_address(),
        nonce=0,
        call_data=call_data,
        call_gas_limit=1,
        verification_gas_limit=2,
        pre_verification_gas=3,
        max_fee_per_gas=4,
        max_priority_fee_per_gas=5,
    )
    context = {SIGNING_CONDITION_OBJECT_CONTEXT_VAR: user_op}

    # Test validation of first element in address array
    condition = SigningObjectAbiAttributeCondition(
        attribute_name="call_data",
        abi_validation=AbiCallValidation(
            {
                "batchTransfer(address[],uint256[])": [
                    AbiParameterValidation(
                        parameter_index=0,
                        sub_indices=[0],  # First element of address[]
                        return_value_test=ReturnValueTest("==", recipient1),
                    )
                ]
            }
        ),
    )

    allowed, _ = condition.verify(providers=condition_provider_manager, **context)
    assert allowed is True

    # Test validation of second element in address array
    condition2 = SigningObjectAbiAttributeCondition(
        attribute_name="call_data",
        abi_validation=AbiCallValidation(
            {
                "batchTransfer(address[],uint256[])": [
                    AbiParameterValidation(
                        parameter_index=0,
                        sub_indices=[1],  # Second element of address[]
                        return_value_test=ReturnValueTest("==", recipient2),
                    )
                ]
            }
        ),
    )

    allowed, _ = condition2.verify(providers=condition_provider_manager, **context)
    assert allowed is True

    # Test validation of uint256 array
    condition3 = SigningObjectAbiAttributeCondition(
        attribute_name="call_data",
        abi_validation=AbiCallValidation(
            {
                "batchTransfer(address[],uint256[])": [
                    AbiParameterValidation(
                        parameter_index=1,
                        sub_indices=[1],  # Second element of uint256[]
                        return_value_test=ReturnValueTest("==", 2000),
                    )
                ]
            }
        ),
    )

    allowed, _ = condition3.verify(providers=condition_provider_manager, **context)
    assert allowed is True


def test_abi_parameter_validation_array_of_tuples(
    condition_provider_manager, get_random_checksum_address
):
    """Test sub_indices for array of tuples (e.g., batch operations)."""

    # Create test data with an array of tuples (address, uint256, bytes)
    recipient1 = get_random_checksum_address()
    recipient2 = get_random_checksum_address()

    # Encode an executeBatch call with array of tuples
    call_data = encode_human_readable_call(
        "executeBatch((address,uint256,bytes)[])",
        [
            [
                (recipient1, 1000000, b"\x00"),
                (recipient2, 2000000, b"\x01"),
            ]
        ],
    )

    user_op = UserOperation(
        sender=get_random_checksum_address(),
        nonce=0,
        call_data=call_data,
        call_gas_limit=1,
        verification_gas_limit=2,
        pre_verification_gas=3,
        max_fee_per_gas=4,
        max_priority_fee_per_gas=5,
    )
    context = {SIGNING_CONDITION_OBJECT_CONTEXT_VAR: user_op}

    # Test validation of amount field (tuple index 1) in first tuple (array index 0)
    # sub_indices=[0, 1] means: array[0] -> tuple[1]
    condition = SigningObjectAbiAttributeCondition(
        attribute_name="call_data",
        abi_validation=AbiCallValidation(
            {
                "executeBatch((address,uint256,bytes)[])": [
                    AbiParameterValidation(
                        parameter_index=0,
                        sub_indices=[0, 1],  # array[0] -> tuple field 1 (uint256)
                        return_value_test=ReturnValueTest("==", 1000000),
                    )
                ]
            }
        ),
    )

    allowed, _ = condition.verify(providers=condition_provider_manager, **context)
    assert allowed is True

    # Test validation of address field (tuple index 0) in second tuple (array index 1)
    condition2 = SigningObjectAbiAttributeCondition(
        attribute_name="call_data",
        abi_validation=AbiCallValidation(
            {
                "executeBatch((address,uint256,bytes)[])": [
                    AbiParameterValidation(
                        parameter_index=0,
                        sub_indices=[1, 0],  # array[1] -> tuple field 0 (address)
                        return_value_test=ReturnValueTest("==", recipient2),
                    )
                ]
            }
        ),
    )

    allowed, _ = condition2.verify(providers=condition_provider_manager, **context)
    assert allowed is True


def test_abi_parameter_validation_tuple_of_arrays(
    condition_provider_manager, get_random_checksum_address
):
    """Test sub_indices for tuple containing arrays - the reverse nesting pattern."""

    # Create test data with a tuple containing arrays
    recipient1 = get_random_checksum_address()
    recipient2 = get_random_checksum_address()

    # Encode a multiTransfer call with tuple of arrays: (address[], uint256[], bytes)
    call_data = encode_human_readable_call(
        "multiTransfer((address[],uint256[],bytes))",
        [
            (
                [recipient1, recipient2],  # address[]
                [1000, 2000],  # uint256[]
                b"\x00",  # bytes
            )
        ],
    )

    user_op = UserOperation(
        sender=get_random_checksum_address(),
        nonce=0,
        call_data=call_data,
        call_gas_limit=1,
        verification_gas_limit=2,
        pre_verification_gas=3,
        max_fee_per_gas=4,
        max_priority_fee_per_gas=5,
    )
    context = {SIGNING_CONDITION_OBJECT_CONTEXT_VAR: user_op}

    # Get second recipient from address array (tuple field 0, then array index 1)
    # sub_indices=[0, 1] means: tuple[0] -> array[1]
    condition = SigningObjectAbiAttributeCondition(
        attribute_name="call_data",
        abi_validation=AbiCallValidation(
            {
                "multiTransfer((address[],uint256[],bytes))": [
                    AbiParameterValidation(
                        parameter_index=0,
                        sub_indices=[0, 1],  # tuple field 0 (address[]) -> array[1]
                        return_value_test=ReturnValueTest("==", recipient2),
                    )
                ]
            }
        ),
    )

    allowed, _ = condition.verify(providers=condition_provider_manager, **context)
    assert allowed is True

    # Get first amount from uint256 array (tuple field 1, then array index 0)
    condition2 = SigningObjectAbiAttributeCondition(
        attribute_name="call_data",
        abi_validation=AbiCallValidation(
            {
                "multiTransfer((address[],uint256[],bytes))": [
                    AbiParameterValidation(
                        parameter_index=0,
                        sub_indices=[1, 0],  # tuple field 1 (uint256[]) -> array[0]
                        return_value_test=ReturnValueTest("==", 1000),
                    )
                ]
            }
        ),
    )

    allowed, _ = condition2.verify(providers=condition_provider_manager, **context)
    assert allowed is True


def test_abi_parameter_validation_sub_indices_out_of_bounds(
    condition_provider_manager, get_random_checksum_address
):
    """Test that array index out of bounds raises error at runtime."""

    # Create test data with a small array
    recipient1 = get_random_checksum_address()

    call_data = encode_human_readable_call(
        "batchTransfer(address[],uint256[])",
        [[recipient1], [1000]],  # Only one element in each array
    )

    user_op = UserOperation(
        sender=get_random_checksum_address(),
        nonce=0,
        call_data=call_data,
        call_gas_limit=1,
        verification_gas_limit=2,
        pre_verification_gas=3,
        max_fee_per_gas=4,
        max_priority_fee_per_gas=5,
    )
    context = {SIGNING_CONDITION_OBJECT_CONTEXT_VAR: user_op}

    # Try to access index 5 when array only has 1 element
    condition = SigningObjectAbiAttributeCondition(
        attribute_name="call_data",
        abi_validation=AbiCallValidation(
            {
                "batchTransfer(address[],uint256[])": [
                    AbiParameterValidation(
                        parameter_index=0,
                        sub_indices=[5],  # Out of bounds at runtime
                        return_value_test=ReturnValueTest("==", recipient1),
                    )
                ]
            }
        ),
    )

    with pytest.raises(ValueError, match="out of range"):
        condition.verify(providers=condition_provider_manager, **context)


def test_signing_object_abi_attribute_condition_initialization():
    condition = SigningObjectAbiAttributeCondition(
        attribute_name="call_data",
        abi_validation=AbiCallValidation(
            {
                "transfer(address,uint256)": [
                    AbiParameterValidation(
                        parameter_index=1, return_value_test=ReturnValueTest("==", 0)
                    )
                ]
            }
        ),
    )

    assert condition.condition_type == ConditionType.SIGNING_ABI_ATTRIBUTE.value
    assert condition.signing_object_context_var == SIGNING_CONDITION_OBJECT_CONTEXT_VAR
    assert condition.attribute_name == "call_data"
    assert list(condition.abi_validation.allowed_abi_calls.keys()) == [
        "transfer(address,uint256)"
    ]
    parameter_checks = condition.abi_validation.allowed_abi_calls[
        "transfer(address,uint256)"
    ]
    assert len(parameter_checks) == 1
    assert parameter_checks[0].parameter_index == 1
    assert parameter_checks[0].return_value_test.comparator == "=="
    assert parameter_checks[0].return_value_test.value == 0


def test_signing_object_abi_attribute_condition_verify_method_call(
    condition_provider_manager, get_random_checksum_address
):
    erc20_transfer_user_op = create_erc20_transfer(
        get_random_checksum_address(),
        0,
        get_random_checksum_address(),
        get_random_checksum_address(),
        10_000_000,
    )
    condition = SigningObjectAbiAttributeCondition(
        attribute_name="callData",
        abi_validation=AbiCallValidation(
            {
                "execute(address,uint256,bytes)": [
                    AbiParameterValidation(
                        parameter_index=2,
                        nested_abi_validation=AbiCallValidation(
                            {
                                "transfer(address,uint256)": [],
                            }
                        ),
                    )
                ],
            }
        ),
    )
    # transfer is allowed
    context = {SIGNING_CONDITION_OBJECT_CONTEXT_VAR: erc20_transfer_user_op}
    allowed, _ = condition.verify(providers=condition_provider_manager, **context)
    assert allowed is True

    # check that approve is not allowed
    erc20_approve_user_op = create_erc20_approve(
        get_random_checksum_address(),
        0,
        get_random_checksum_address(),
        get_random_checksum_address(),
        1_000_000,
    )
    context = {SIGNING_CONDITION_OBJECT_CONTEXT_VAR: erc20_approve_user_op}

    allowed, _ = condition.verify(providers=condition_provider_manager, **context)
    assert allowed is False


def test_signing_object_abi_attribute_condition_verify_transfer_eth_to_address_call(
    condition_provider_manager, get_random_checksum_address
):
    allowed_addresses = [
        get_random_checksum_address(),
        get_random_checksum_address(),
        get_random_checksum_address(),
    ]
    sender = get_random_checksum_address()
    nonce = 0
    amount = 10_000_000

    eth_transfer_user_op = create_eth_transfer(
        sender, nonce, random.choice(allowed_addresses), amount
    )
    condition = SigningObjectAbiAttributeCondition(
        attribute_name="callData",
        abi_validation=AbiCallValidation(
            {
                "execute(address,uint256,bytes)": [
                    AbiParameterValidation(
                        parameter_index=0,
                        return_value_test=ReturnValueTest("in", allowed_addresses),
                    )
                ]
            }
        ),
    )
    context = {SIGNING_CONDITION_OBJECT_CONTEXT_VAR: eth_transfer_user_op}
    allowed, result = condition.verify(providers=condition_provider_manager, **context)
    assert allowed is True

    not_allowed_address = get_random_checksum_address()
    eth_transfer_to_not_allowed_user_op = create_eth_transfer(
        sender, nonce, not_allowed_address, amount
    )
    context = {
        SIGNING_CONDITION_OBJECT_CONTEXT_VAR: eth_transfer_to_not_allowed_user_op
    }
    allowed, result = condition.verify(providers=condition_provider_manager, **context)
    assert allowed is False


def test_signing_object_abi_attribute_condition_verify_transfer_eth_amount_call(
    condition_provider_manager, get_random_checksum_address
):
    sender = get_random_checksum_address()
    nonce = 22
    to_address = get_random_checksum_address()

    eth_transfer_user_op = create_eth_transfer(sender, nonce, to_address, 10_000_000)
    condition = SigningObjectAbiAttributeCondition(
        attribute_name="callData",
        abi_validation=AbiCallValidation(
            {
                "execute(address,uint256,bytes)": [
                    AbiParameterValidation(
                        parameter_index=1,
                        return_value_test=ReturnValueTest("<", 20_000_000),
                    )
                ]
            }
        ),
    )
    context = {SIGNING_CONDITION_OBJECT_CONTEXT_VAR: eth_transfer_user_op}
    allowed, result = condition.verify(providers=condition_provider_manager, **context)
    assert allowed is True

    eth_transfer_to_large_user_op = create_eth_transfer(
        sender, nonce, to_address, 30_000_000
    )
    context = {SIGNING_CONDITION_OBJECT_CONTEXT_VAR: eth_transfer_to_large_user_op}
    allowed, result = condition.verify(providers=condition_provider_manager, **context)
    assert allowed is False


def test_signing_object_abi_attribute_condition_nested_erc20_transfer_restriction(
    condition_provider_manager, get_random_checksum_address
):
    erc20_token_address = get_random_checksum_address()
    to_address = get_random_checksum_address()
    amount = int(Web3.to_wei(1, "ether"))

    condition = SigningObjectAbiAttributeCondition(
        attribute_name="call_data",
        abi_validation=AbiCallValidation(
            {
                "execute(address,uint256,bytes)": [
                    # only allow specific token address
                    AbiParameterValidation(
                        parameter_index=0,
                        return_value_test=ReturnValueTest("==", erc20_token_address),
                    ),
                    AbiParameterValidation(
                        parameter_index=2,
                        nested_abi_validation=AbiCallValidation(
                            {
                                "transfer(address,uint256)": [
                                    # only allow transfer to specific recipient
                                    AbiParameterValidation(
                                        parameter_index=0,
                                        return_value_test=ReturnValueTest(
                                            "==", to_address
                                        ),
                                    ),
                                    # only allow < 2 eth to be transferred
                                    AbiParameterValidation(
                                        parameter_index=1,
                                        return_value_test=ReturnValueTest(
                                            "<", int(Web3.to_wei(2, "ether"))
                                        ),
                                    ),
                                ]
                            }
                        ),
                    ),
                ]
            }
        ),
    )

    base_user_op_dict = dict(
        sender=get_random_checksum_address(),
        nonce=76,
        token=erc20_token_address,
        to=to_address,
        amount=amount,
    )

    # success case
    user_op = create_erc20_transfer(**base_user_op_dict)
    context = {SIGNING_CONDITION_OBJECT_CONTEXT_VAR: user_op}
    allowed, _ = condition.verify(providers=condition_provider_manager, **context)
    assert allowed is True

    # modify user op for check to fail
    # 1) all the same except different token address
    fail_user_op_dict = copy.deepcopy(base_user_op_dict)
    fail_user_op_dict["token"] = get_random_checksum_address()
    fail_user_op = create_erc20_transfer(**fail_user_op_dict)

    context = {SIGNING_CONDITION_OBJECT_CONTEXT_VAR: fail_user_op}
    allowed, _ = condition.verify(providers=condition_provider_manager, **context)
    assert allowed is False

    # 2) all the same except recipient
    fail_user_op_dict = copy.deepcopy(base_user_op_dict)
    fail_user_op_dict["to"] = get_random_checksum_address()
    fail_user_op = create_erc20_transfer(**fail_user_op_dict)

    context = {SIGNING_CONDITION_OBJECT_CONTEXT_VAR: fail_user_op}
    allowed, _ = condition.verify(providers=condition_provider_manager, **context)
    assert allowed is False

    # 3) all the same except amount too high
    fail_user_op_dict = copy.deepcopy(base_user_op_dict)
    fail_user_op_dict["amount"] = int(Web3.to_wei(3, "ether"))
    fail_user_op = create_erc20_transfer(**fail_user_op_dict)

    context = {SIGNING_CONDITION_OBJECT_CONTEXT_VAR: fail_user_op}
    allowed, _ = condition.verify(providers=condition_provider_manager, **context)
    assert allowed is False

    # 4) approve user op instead of a transfer (note: only transfer user op is allowed)
    fail_user_op_dict = copy.deepcopy(base_user_op_dict)
    del fail_user_op_dict["to"]  # approve doesn't have a "to" field
    fail_user_op_dict["spender"] = get_random_checksum_address()
    fail_user_op = create_erc20_approve(**fail_user_op_dict)

    context = {SIGNING_CONDITION_OBJECT_CONTEXT_VAR: fail_user_op}
    allowed, _ = condition.verify(providers=condition_provider_manager, **context)
    assert allowed is False


def test_signing_object_abi_attribute_condition_more_than_2_levels_nested_calldata(
    mocker, condition_provider_manager, get_random_checksum_address
):
    # Level 3: innermost transfer() call
    transfer_data = encode_function_call(
        "transfer(address,uint256)", [get_random_checksum_address(), 10_000_000]
    )

    # Level 2: eg. proxy.execute(token_address, 0, transfer_data)
    proxy_execute_data = encode_function_call(
        "execute((address,uint256,bytes))",
        [(get_random_checksum_address(), 0, transfer_data)],
    )

    # Level 1: smartAccount.execute(proxy_address, 0, proxy_execute_data)
    proxy_address = get_random_checksum_address()
    user_op_call_data = encode_function_call(
        "execute(address,uint256,bytes)", [proxy_address, 0, proxy_execute_data]
    )

    condition = SigningObjectAbiAttributeCondition(
        attribute_name="call_data",
        abi_validation=AbiCallValidation(
            {
                "execute(address,uint256,bytes)": [
                    # only allow proxy address
                    AbiParameterValidation(
                        0, return_value_test=ReturnValueTest("==", proxy_address)
                    ),
                    AbiParameterValidation(
                        2,
                        nested_abi_validation=AbiCallValidation(
                            {
                                "execute((address,uint256,bytes))": [
                                    # only allow transfer call
                                    AbiParameterValidation(
                                        parameter_index=0,
                                        sub_indices=[2],
                                        nested_abi_validation=AbiCallValidation(
                                            {"transfer(address,uint256)": []}
                                        ),
                                    )
                                ]
                            }
                        ),
                    ),
                ]
            }
        ),
    )

    signing_object = mocker.Mock()
    signing_object.call_data = user_op_call_data
    context = {SIGNING_CONDITION_OBJECT_CONTEXT_VAR: signing_object}
    allowed, _ = condition.verify(providers=condition_provider_manager, **context)
    assert allowed is True

    # failure case: try calling some other function from the proxy eg. call a contract function
    contract_call = encode_function_call(
        "execute(address,uint256,bytes)",
        [get_random_checksum_address(), 0, encode_function_call("getValue()", [])],
    )
    updated_proxy_execute_data = encode_function_call(
        "execute(address,uint256,bytes)",
        [get_random_checksum_address(), 0, contract_call],
    )
    updated_user_op_call_data = encode_function_call(
        "execute(address,uint256,bytes)", [proxy_address, 0, updated_proxy_execute_data]
    )
    signing_object.call_data = updated_user_op_call_data
    context = {SIGNING_CONDITION_OBJECT_CONTEXT_VAR: signing_object}
    allowed, _ = condition.verify(providers=condition_provider_manager, **context)
    assert allowed is False


def test_signing_object_abi_attribute_condition_tuple_index(
    mocker, condition_provider_manager
):
    # example contract call
    # {
    #   to: "0xBa0c733Ab8328baD95e5708159eB55C4ec1Aae26",
    #   value: 0n,
    #   data: "0x42cde4e8",   <threshold() function call>
    # }
    expected_contract_address = "0xBa0c733Ab8328baD95e5708159eB55C4ec1Aae26"
    call_data_from_script = encode_function_call(
        # this is how the user op is created in the MDT demo
        "execute((address,uint256,bytes))",
        [(expected_contract_address, 0, encode_function_call("threshold()", []))],
    )

    signing_object = mocker.Mock()
    signing_object.call_data = bytes(call_data_from_script)
    context = {SIGNING_CONDITION_OBJECT_CONTEXT_VAR: signing_object}

    condition = SigningObjectAbiAttributeCondition(
        attribute_name="call_data",
        abi_validation=AbiCallValidation(
            {
                "execute((address,uint256,bytes))": [
                    AbiParameterValidation(
                        parameter_index=0,
                        sub_indices=[0],
                        return_value_test=ReturnValueTest(
                            "==", expected_contract_address
                        ),
                    ),
                    AbiParameterValidation(
                        parameter_index=0,
                        sub_indices=[2],
                        nested_abi_validation=AbiCallValidation({"threshold()": []}),
                    ),
                ]
            }
        ),
    )

    allowed, _ = condition.verify(providers=condition_provider_manager, **context)
    assert allowed is True


def test_signing_object_abi_attribute_condition_lingo_json_serialization(
    mocker, condition_provider_manager, get_random_checksum_address
):
    """Test serializing and deserializing a condition lingo with ECDSA condition"""
    call_data_human_signature = "transfer(address,uint256)"
    signing_object = mocker.Mock()
    signing_object.call_data = encode_human_readable_call(
        call_data_human_signature, [get_random_checksum_address(), 10_000_000]
    )

    condition = SigningObjectAbiAttributeCondition(
        attribute_name="call_data",
        abi_validation=AbiCallValidation(
            {
                "transfer(address,uint256)": [
                    AbiParameterValidation(
                        parameter_index=1,
                        return_value_test=ReturnValueTest("<", 20_000_000),
                    )
                ]
            }
        ),
    )
    context = {SIGNING_CONDITION_OBJECT_CONTEXT_VAR: signing_object}

    allowed, result = condition.verify(providers=condition_provider_manager, **context)
    assert allowed is True

    # Create condition lingo
    lingo = ConditionLingo(condition)

    # Convert lingo to JSON
    original_lingo_json = lingo.to_json()

    # Parse JSON to dict and verify structure
    lingo_dict = json.loads(original_lingo_json)
    assert lingo_dict["version"] == ConditionLingo.VERSION
    assert (
        lingo_dict["condition"]["conditionType"]
        == ConditionType.SIGNING_ABI_ATTRIBUTE.value
    )

    # Recreate lingo from JSON
    recreated_lingo = ConditionLingo.from_json(original_lingo_json)
    assert recreated_lingo.to_json() == original_lingo_json

    # works the same
    allowed, result = recreated_lingo.condition.verify(
        providers=condition_provider_manager, **context
    )
    assert allowed is True


def test_signing_restriction_based_points_value_from_rest_endpoint(
    mocker, get_random_checksum_address, condition_provider_manager
):
    expected_total_points = 5600 + 4410 + 0  # sum of points from the mocked response

    endpoint_points_response = {
        "servers": [
            {
                "_id": "1234",
                "guildId": "111111",
                "points": 5600,
                "guildName": "The Ones",
            },
            {
                "_id": "5678",
                "guildId": "222222",
                "points": 4410,
                "guildName": "The Twos",
            },
            {
                "_id": "91011",
                "guildId": "333333",
                "points": 0,
                "guildName": "The Threes",
            },
        ],
        "usage": 1,
        "limit": 2000,
    }

    mocked_get = mocker.patch(
        "requests.get",
        return_value=mocker.Mock(
            status_code=200, json=lambda: endpoint_points_response
        ),
    )

    # JSON conditions
    json_condition = JsonApiCondition(
        endpoint="https://www.endpoint.io/api/v1/points",
        query="$.servers[*].points",
        authorization_token=":authToken",
        authorization_type=AuthorizationType.X_API_KEY,
        return_value_test=ReturnValueTest(
            comparator=">",
            value=0,
            operations=[
                VariableOperation(operation="sum"),  # sum all points
            ],
        ),
    )

    # ECDSA condition
    # random signing key (a bot will have one of their own)
    signing_key = SigningKey.generate(curve=SECP256k1)
    verifying_key = signing_key.verifying_key

    # the bot will sign a message
    test_message = b"This is a test message for ECDSA verification"
    test_signature = signing_key.sign(
        test_message,
        hashfunc=ECDSAVerificationCall._hash_func,
        sigencode=sigencode_string,
    )
    ecdsa_condition = ECDSACondition(
        message=":ecdsaMessage",
        signature=":ecdsaSignature",
        verifying_key=verifying_key.to_string().hex(),
        curve=SECP256k1.name,
    )

    # Signing ABI condition
    erc20_token_address = get_random_checksum_address()
    amount = expected_total_points * (10**18)

    signing_abi_condition = SigningObjectAbiAttributeCondition(
        attribute_name="call_data",
        abi_validation=AbiCallValidation(
            allowed_abi_calls={
                "execute(address,uint256,bytes)": [
                    # only allow specific token address
                    AbiParameterValidation(
                        parameter_index=0,
                        return_value_test=ReturnValueTest("==", erc20_token_address),
                    ),
                    AbiParameterValidation(
                        parameter_index=2,
                        nested_abi_validation=AbiCallValidation(
                            allowed_abi_calls={
                                "transfer(address,uint256)": [
                                    AbiParameterValidation(
                                        parameter_index=1,
                                        return_value_test=ReturnValueTest(
                                            # TODO expectation is that points is already in wei
                                            #  (can't do ether -> wei conversion as part of condition)
                                            "==",
                                            ":points",
                                        ),
                                    ),
                                ]
                            }
                        ),
                    ),
                ]
            }
        ),
    )

    sequential_condition = SequentialCondition(
        condition_variables=[
            ConditionVariable(var_name="ecdsa", condition=ecdsa_condition),
            ConditionVariable(
                var_name="points",
                condition=json_condition,
                operations=[
                    VariableOperation(operation="sum"),
                    VariableOperation(operation="ethToWei"),  # convert to wei
                ],
            ),
            ConditionVariable(var_name="signingAbi", condition=signing_abi_condition),
        ]
    )

    # create user operation based on values (this would be done by the bot)
    user_op = create_erc20_transfer(
        sender=get_random_checksum_address(),
        nonce=76,
        token=erc20_token_address,
        to=get_random_checksum_address(),
        amount=amount,
    )

    # create context for conditions (application-specific
    # logic for getting token and adding to context)
    context = {
        ":authToken": "1234567890abcdef",
        ":ecdsaMessage": HexBytes(test_message).hex(),  # must be 0x prefixed for bytes
        ":ecdsaSignature": test_signature.hex(),
        SIGNING_CONDITION_OBJECT_CONTEXT_VAR: user_op,
    }

    # verify sequential condition
    allowed, values = sequential_condition.verify(
        providers=condition_provider_manager, **context
    )

    assert allowed is True
    assert values == [
        None,
        [5600, 4410, 0],  # points from the mocked response,
        # TODO: in abi encoding, address values are lowercase hence the
        #  return value of parameter check from condition is lowercase
        [erc20_token_address.lower(), [amount]],
    ]
    assert mocked_get.call_count == 1
