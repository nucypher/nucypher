import copy
import json
import random

import pytest
from web3 import Web3

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
        condition_type=ConditionType.ATTRIBUTE.value,
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
    assert lingo_dict["condition"]["conditionType"] == ConditionType.ATTRIBUTE.value

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
    with pytest.raises(InvalidCondition, match=ConditionType.ABI_ATTRIBUTE.value):
        _ = SigningObjectAbiAttributeCondition(
            condition_type=ConditionType.TIME.value,
            attribute_name="call_data",
            abi_validation=AbiCallValidation({"transfer(address,uint256)": []}),
        )

    # no allowed abi calls
    with pytest.raises(InvalidCondition, match="Missing data for required field"):
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

    # invalid tuple arg
    with pytest.raises(ValueError, match="is not a tuple"):
        _ = SigningObjectAbiAttributeCondition(
            attribute_name="call_data",
            abi_validation=AbiCallValidation(
                {
                    "execute(address,uint256,bytes)": [
                        AbiParameterValidation(
                            parameter_index=0,
                            index_within_tuple=0,
                            return_value_test=ReturnValueTest("==", 0),
                        )
                    ]
                }
            ),
        )

    # tuple index out of range
    with pytest.raises(
        ValueError, match="Tuple value index '3' for parameter is out of range"
    ):
        _ = SigningObjectAbiAttributeCondition(
            attribute_name="call_data",
            abi_validation=AbiCallValidation(
                {
                    "execute((address,uint256,bytes))": [
                        AbiParameterValidation(
                            parameter_index=0,
                            index_within_tuple=3,
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

    assert condition.condition_type == ConditionType.ABI_ATTRIBUTE.value
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


def test_signing_object_abi_attribute_condition_invalid_value_for_call_data_check(
    condition_provider_manager, get_random_checksum_address
):
    eth_transfer_user_op = create_eth_transfer(
        get_random_checksum_address(), 0, get_random_checksum_address(), 10_000_000
    )
    condition = SigningObjectAbiAttributeCondition(
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
    context = {SIGNING_CONDITION_OBJECT_CONTEXT_VAR: eth_transfer_user_op}
    with pytest.raises(
        InvalidCondition, match="Invalid data type for checking call data"
    ):
        _, _ = condition.verify(providers=condition_provider_manager, **context)


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
                        2,
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
        "execute(address,uint256,bytes)",
        [get_random_checksum_address(), 0, transfer_data],
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
                                "execute(address,uint256,bytes)": [
                                    # only allow transfer call
                                    AbiParameterValidation(
                                        2,
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
                        index_within_tuple=0,
                        return_value_test=ReturnValueTest(
                            "==", expected_contract_address
                        ),
                    ),
                    AbiParameterValidation(
                        parameter_index=0,
                        index_within_tuple=2,
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
    assert lingo_dict["condition"]["conditionType"] == ConditionType.ABI_ATTRIBUTE.value

    # Recreate lingo from JSON
    recreated_lingo = ConditionLingo.from_json(original_lingo_json)
    assert recreated_lingo.to_json() == original_lingo_json

    # works the same
    allowed, result = recreated_lingo.condition.verify(
        providers=condition_provider_manager, **context
    )
    assert allowed is True
