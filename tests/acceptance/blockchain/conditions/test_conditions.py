"""
 This file is part of nucypher.

 nucypher is free software: you can redistribute it and/or modify
 it under the terms of the GNU Affero General Public License as published by
 the Free Software Foundation, either version 3 of the License, or
 (at your option) any later version.

 nucypher is distributed in the hope that it will be useful,
 but WITHOUT ANY WARRANTY; without even the implied warranty of
 MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
 GNU Affero General Public License for more details.

 You should have received a copy of the GNU Affero General Public License
 along with nucypher.  If not, see <https://www.gnu.org/licenses/>.
"""
import copy
import json
import os
from unittest import mock

import pytest
from web3 import Web3

from nucypher.policy.conditions.context import (
    USER_ADDRESS_CONTEXT,
    ContextVariableVerificationFailed,
    InvalidContextVariableData,
    RequiredContextVariable,
    _recover_user_address,
)
from nucypher.policy.conditions.evm import RPCCondition, get_context_value
from nucypher.policy.conditions.lingo import ConditionLingo, ReturnValueTest
from tests.integration.characters.test_bob_handles_frags import _make_message_kits

VALID_USER_ADDRESS_CONTEXT = {
    USER_ADDRESS_CONTEXT: {
        "signature": "0x488a7acefdc6d098eedf73cdfd379777c0f4a4023a660d350d3bf309a51dd4251abaad9cdd11b71c400cfb4625c14ca142f72b39165bd980c8da1ea32892ff071c",
        "address": "0x5ce9454909639D2D17A3F753ce7d93fa0b9aB12E",
        "typedData": {
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
                "name": "tDec",
                "version": "1",
                "chainId": 80001,
                "salt": "0x3e6365d35fd4e53cbc00b080b0742b88f8b735352ea54c0534ed6a2e44a83ff0",
            },
            "message": {
                "address": "0x5ce9454909639D2D17A3F753ce7d93fa0b9aB12E",
                "blockNumber": 28117088,
                "blockHash": "0x104dfae58be4a9b15d59ce447a565302d5658914f1093f10290cd846fbe258b7",
                "signatureText": "I'm the owner of address 0x5ce9454909639D2D17A3F753ce7d93fa0b9aB12E as of block number 28117088",
            },
        },
    }
}


def _dont_validate_user_address(context_variable: str, **context):
    if context_variable == USER_ADDRESS_CONTEXT:
        return context[USER_ADDRESS_CONTEXT]["address"]
    return get_context_value(context_variable, **context)


def test_required_context_variable(
    testerchain, custom_context_variable_erc20_condition
):
    with pytest.raises(RequiredContextVariable):
        custom_context_variable_erc20_condition.verify(
            provider=testerchain.provider
        )  # no context


@pytest.mark.parametrize("expected_entry", ["address", "signature", "typedData"])
def test_user_address_context_missing_required_entries(expected_entry):
    context = copy.deepcopy(VALID_USER_ADDRESS_CONTEXT)
    del context[USER_ADDRESS_CONTEXT][expected_entry]
    with pytest.raises(InvalidContextVariableData):
        _recover_user_address(**context)


def test_user_address_context_invalid_eip712_typed_data():
    # invalid typed data
    context = copy.deepcopy(VALID_USER_ADDRESS_CONTEXT)
    context[USER_ADDRESS_CONTEXT]["typedData"] = dict(
        randomSaying="Comparison is the thief of joy."  # -– Theodore Roosevelt
    )
    with pytest.raises(InvalidContextVariableData):
        _recover_user_address(**context)


def test_user_address_context_variable_verification(testerchain):
    # valid user address context - signature matches address
    address = _recover_user_address(**VALID_USER_ADDRESS_CONTEXT)
    assert address == VALID_USER_ADDRESS_CONTEXT[USER_ADDRESS_CONTEXT]["address"]

    # invalid user address context - signature does not match address
    # internals are mutable - deepcopy
    mismatch_with_address_context = copy.deepcopy(VALID_USER_ADDRESS_CONTEXT)
    mismatch_with_address_context[USER_ADDRESS_CONTEXT][
        "address"
    ] = testerchain.etherbase_account
    with pytest.raises(ContextVariableVerificationFailed):
        _recover_user_address(**mismatch_with_address_context)

    # invalid user address context - signature does not match address
    # internals are mutable - deepcopy
    mismatch_with_address_context = copy.deepcopy(VALID_USER_ADDRESS_CONTEXT)
    signature = (
        "0x93252ddff5f90584b27b5eef1915b23a8b01a703be56c8bf0660647c15cb75e9"
        "1983bde9877eaad11da5a3ebc9b64957f1c182536931f9844d0c600f0c41293d1b"
    )
    mismatch_with_address_context[USER_ADDRESS_CONTEXT]["signature"] = signature
    with pytest.raises(ContextVariableVerificationFailed):
        _recover_user_address(**mismatch_with_address_context)

    # invalid signature
    # internals are mutable - deepcopy
    invalid_signature_context = copy.deepcopy(VALID_USER_ADDRESS_CONTEXT)
    invalid_signature_context[USER_ADDRESS_CONTEXT][
        "signature"
    ] = "0xdeadbeef"  # invalid signature
    with pytest.raises(ContextVariableVerificationFailed):
        _recover_user_address(**invalid_signature_context)


@mock.patch(
    "nucypher.policy.conditions.evm.get_context_value",
    side_effect=_dont_validate_user_address,
)
def test_rpc_condition_evaluation(get_context_value_mock, testerchain, rpc_condition):
    context = {USER_ADDRESS_CONTEXT: {"address": testerchain.unassigned_accounts[0]}}
    result, value = rpc_condition.verify(provider=testerchain.provider, **context)
    assert result is True
    assert value == Web3.toWei(
        1_000_000, "ether"
    )  # same value used in rpc_condition fixture


@mock.patch(
    "nucypher.policy.conditions.evm.get_context_value",
    side_effect=_dont_validate_user_address,
)
def test_rpc_condition_evaluation_with_context_var_in_return_value_test(
    get_context_value_mock, testerchain
):
    account, *other_accounts = testerchain.client.accounts
    balance = testerchain.client.get_balance(account)

    # we have balance stored, use for rpc condition with context variable
    rpc_condition = RPCCondition(
        method="eth_getBalance",
        chain="testerchain",
        return_value_test=ReturnValueTest(
            "==", ":balanceContextVar"
        ),  # user-defined context var
        parameters=[USER_ADDRESS_CONTEXT],
    )
    context = {
        USER_ADDRESS_CONTEXT: {"address": account},
        ":balanceContextVar": balance,
    }
    result, value = rpc_condition.verify(provider=testerchain.provider, **context)
    assert result
    assert value == balance

    # modify balance to make it false
    invalid_balance = balance + 1
    context[":balanceContextVar"] = invalid_balance
    result, value = rpc_condition.verify(provider=testerchain.provider, **context)
    assert not result
    assert value != invalid_balance


@mock.patch(
    "nucypher.policy.conditions.evm.get_context_value",
    side_effect=_dont_validate_user_address,
)
def test_erc20_evm_condition_evaluation(
    get_context_value_mock, testerchain, erc20_evm_condition
):
    context = {USER_ADDRESS_CONTEXT: {"address": testerchain.unassigned_accounts[0]}}
    result, value = erc20_evm_condition.verify(provider=testerchain.provider, **context)
    assert result is True

    context[USER_ADDRESS_CONTEXT]["address"] = testerchain.etherbase_account
    result, value = erc20_evm_condition.verify(provider=testerchain.provider, **context)
    assert result is False


def test_erc20_evm_condition_evaluation_with_custom_context_variable(
    testerchain, custom_context_variable_erc20_condition
):
    context = {":addressToUse": testerchain.unassigned_accounts[0]}
    result, value = custom_context_variable_erc20_condition.verify(
        provider=testerchain.provider, **context
    )
    assert result is True

    context[":addressToUse"] = testerchain.etherbase_account
    result, value = custom_context_variable_erc20_condition.verify(
        provider=testerchain.provider, **context
    )
    assert result is False


@mock.patch(
    "nucypher.policy.conditions.evm.get_context_value",
    side_effect=_dont_validate_user_address,
)
def test_erc721_evm_condition_owner_evaluation(
    get_context_value_mock, testerchain, test_registry, erc721_evm_condition_owner
):
    account, *other_accounts = testerchain.client.accounts
    # valid owner of nft
    context = {USER_ADDRESS_CONTEXT: {"address": account}}
    result, value = erc721_evm_condition_owner.verify(
        provider=testerchain.provider, **context
    )
    assert result
    assert value == account

    # invalid owner of nft
    other_account = other_accounts[0]
    context = {USER_ADDRESS_CONTEXT: {"address": other_account}}
    result, value = erc721_evm_condition_owner.verify(
        provider=testerchain.provider, **context
    )
    assert not result
    assert value != other_account


@mock.patch(
    "nucypher.policy.conditions.evm.get_context_value",
    side_effect=_dont_validate_user_address,
)
def test_erc721_evm_condition_balanceof_evaluation(
    get_context_value_mock, testerchain, test_registry, erc721_evm_condition_balanceof
):
    account, *other_accounts = testerchain.client.accounts
    context = {USER_ADDRESS_CONTEXT: {"address": account}}  # owner of NFT
    result, value = erc721_evm_condition_balanceof.verify(
        provider=testerchain.provider, **context
    )
    assert result

    # invalid owner of nft
    other_account = other_accounts[0]  # not an owner of NFT
    context = {USER_ADDRESS_CONTEXT: {"address": other_account}}
    result, value = erc721_evm_condition_balanceof.verify(
        provider=testerchain.provider, **context
    )
    assert not result


def test_subscription_manager_condition_evaluation(
    testerchain, enacted_blockchain_policy, subscription_manager_condition
):
    context = {
        ":hrac": bytes(enacted_blockchain_policy.hrac)
    }  # user-defined context var
    result, value = subscription_manager_condition.verify(
        provider=testerchain.provider, **context
    )
    assert value
    assert result

    # non-active policy hrac
    context[":hrac"] = os.urandom(16)
    result, value = subscription_manager_condition.verify(
        provider=testerchain.provider, **context
    )
    assert not value
    assert not result


@mock.patch(
    "nucypher.policy.conditions.evm.get_context_value",
    side_effect=_dont_validate_user_address,
)
def test_time_condition_evaluation(
    get_context_value_mock, testerchain, timelock_condition
):
    context = {USER_ADDRESS_CONTEXT: {"address": testerchain.unassigned_accounts[0]}}
    result, value = timelock_condition.verify(provider=testerchain.provider, **context)
    assert result is True


def test_simple_compound_conditions_evaluation(testerchain):
    # TODO Improve internals of evaluation here (natural vs recursive approach)
    conditions = [
        {'returnValueTest': {'value': '0', 'comparator': '>'}, 'method': 'timelock'},
        {'operator': 'and'},
        {'returnValueTest': {'value': '99999999999999999', 'comparator': '<'}, 'method': 'timelock'},
        {'operator': 'and'},
        {'returnValueTest': {'value': '0', 'comparator': '>'}, 'method': 'timelock'}
    ]
    conditions = json.dumps(conditions)
    lingo = ConditionLingo.from_json(conditions)
    result = lingo.eval()
    assert result is True


@mock.patch(
    "nucypher.policy.conditions.evm.get_context_value",
    side_effect=_dont_validate_user_address,
)
def test_onchain_conditions_lingo_evaluation(
    get_context_value_mock,
    testerchain,
    lingo,
):
    context = {USER_ADDRESS_CONTEXT: {"address": testerchain.etherbase_account}}
    result = lingo.eval(provider=testerchain.provider, **context)
    assert result is True


def test_single_retrieve_with_onchain_conditions(enacted_blockchain_policy, blockchain_bob, blockchain_ursulas):
    blockchain_bob.start_learning_loop()
    conditions = [
        {'returnValueTest': {'value': '0', 'comparator': '>'}, 'method': 'timelock'},
        {'operator': 'and'},
        {"chain": "testerchain",
         "method": "eth_getBalance",
         "parameters": [
             blockchain_bob.checksum_address,
             "latest"
         ],
         "returnValueTest": {
             "comparator": ">=",
             "value": "10000000000000"
         }
        }

    ]
    messages, message_kits = _make_message_kits(enacted_blockchain_policy.public_key, conditions)
    policy_info_kwargs = dict(
        encrypted_treasure_map=enacted_blockchain_policy.treasure_map,
        alice_verifying_key=enacted_blockchain_policy.publisher_verifying_key,
    )

    cleartexts = blockchain_bob.retrieve_and_decrypt(
        message_kits=message_kits,
        **policy_info_kwargs,
    )

    assert cleartexts == messages
