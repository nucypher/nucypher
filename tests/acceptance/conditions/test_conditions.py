import copy
import json
import os
from unittest import mock

import pytest
from web3 import Web3

from nucypher.blockchain.eth.agents import ContractAgency, SubscriptionManagerAgent
from nucypher.blockchain.eth.constants import NULL_ADDRESS
from nucypher.policy.conditions.context import (
    USER_ADDRESS_CONTEXT,
    _recover_user_address,
)
from nucypher.policy.conditions.evm import (
    ContractCondition,
    RPCCondition,
    get_context_value,
)
from nucypher.policy.conditions.exceptions import (
    ContextVariableVerificationFailed,
    InvalidContextVariableData,
    NoConnectionToChain,
    RequiredContextVariable,
    RPCExecutionFailed,
)
from nucypher.policy.conditions.lingo import (
    ConditionLingo,
    ConditionType,
    NotCompoundCondition,
    ReturnValueTest,
)
from tests.constants import (
    TEST_ETH_PROVIDER_URI,
    TEST_POLYGON_PROVIDER_URI,
    TESTERCHAIN_CHAIN_ID,
)
from tests.utils.policy import make_message_kits


def _dont_validate_user_address(context_variable: str, **context):
    if context_variable == USER_ADDRESS_CONTEXT:
        return context[USER_ADDRESS_CONTEXT]["address"]
    return get_context_value(context_variable, **context)


def test_required_context_variable(
    custom_context_variable_erc20_condition, condition_providers
):
    with pytest.raises(RequiredContextVariable):
        custom_context_variable_erc20_condition.verify(
            providers=condition_providers
        )  # no context


@pytest.mark.parametrize("expected_entry", ["address", "signature", "typedData"])
def test_user_address_context_missing_required_entries(expected_entry, valid_user_address_context):
    context = copy.deepcopy(valid_user_address_context)
    del context[USER_ADDRESS_CONTEXT][expected_entry]
    with pytest.raises(InvalidContextVariableData):
        _recover_user_address(**context)


def test_user_address_context_invalid_eip712_typed_data(valid_user_address_context):
    # invalid typed data
    context = copy.deepcopy(valid_user_address_context)
    context[USER_ADDRESS_CONTEXT]["typedData"] = dict(
        randomSaying="Comparison is the thief of joy."  # -– Theodore Roosevelt
    )
    with pytest.raises(InvalidContextVariableData):
        _recover_user_address(**context)


def test_user_address_context_variable_verification(testerchain, valid_user_address_context):
    # valid user address context - signature matches address
    address = _recover_user_address(**valid_user_address_context)
    assert address == valid_user_address_context[USER_ADDRESS_CONTEXT]["address"]

    # invalid user address context - signature does not match address
    # internals are mutable - deepcopy
    mismatch_with_address_context = copy.deepcopy(valid_user_address_context)
    mismatch_with_address_context[USER_ADDRESS_CONTEXT][
        "address"
    ] = testerchain.etherbase_account
    with pytest.raises(ContextVariableVerificationFailed):
        _recover_user_address(**mismatch_with_address_context)

    # invalid user address context - signature does not match address
    # internals are mutable - deepcopy
    mismatch_with_address_context = copy.deepcopy(valid_user_address_context)
    signature = (
        "0x93252ddff5f90584b27b5eef1915b23a8b01a703be56c8bf0660647c15cb75e9"
        "1983bde9877eaad11da5a3ebc9b64957f1c182536931f9844d0c600f0c41293d1b"
    )
    mismatch_with_address_context[USER_ADDRESS_CONTEXT]["signature"] = signature
    with pytest.raises(ContextVariableVerificationFailed):
        _recover_user_address(**mismatch_with_address_context)

    # invalid signature
    # internals are mutable - deepcopy
    invalid_signature_context = copy.deepcopy(valid_user_address_context)
    invalid_signature_context[USER_ADDRESS_CONTEXT][
        "signature"
    ] = "0xdeadbeef"  # invalid signature
    with pytest.raises(ContextVariableVerificationFailed):
        _recover_user_address(**invalid_signature_context)


@mock.patch(
    "nucypher.policy.conditions.evm.get_context_value",
    side_effect=_dont_validate_user_address,
)
def test_rpc_condition_evaluation(get_context_value_mock, testerchain, rpc_condition, condition_providers):
    context = {USER_ADDRESS_CONTEXT: {"address": testerchain.unassigned_accounts[0]}}
    condition_result, call_result = rpc_condition.verify(
        providers=condition_providers, **context
    )
    assert condition_result is True
    assert call_result == Web3.to_wei(
        1_000_000, "ether"
    )  # same value used in rpc_condition fixture


@mock.patch(
    "nucypher.policy.conditions.evm.get_context_value",
    side_effect=_dont_validate_user_address,
)
def test_rpc_condition_evaluation_no_connection_to_chain(
    get_context_value_mock, testerchain, rpc_condition
):
    context = {USER_ADDRESS_CONTEXT: {"address": testerchain.unassigned_accounts[0]}}

    # condition providers for other unrelated chains
    providers = {
        1: mock.Mock(),  # mainnet
        5: mock.Mock(),  # Goerli
    }

    with pytest.raises(NoConnectionToChain):
        rpc_condition.verify(providers=providers, **context)


@mock.patch(
    "nucypher.policy.conditions.evm.get_context_value",
    side_effect=_dont_validate_user_address,
)
def test_rpc_condition_evaluation_with_context_var_in_return_value_test(
    get_context_value_mock, testerchain, condition_providers
):
    account, *other_accounts = testerchain.client.accounts
    balance = testerchain.client.get_balance(account)

    # we have balance stored, use for rpc condition with context variable
    rpc_condition = RPCCondition(
        method="eth_getBalance",
        chain=TESTERCHAIN_CHAIN_ID,
        return_value_test=ReturnValueTest(
            "==", ":balanceContextVar"
        ),  # user-defined context var
        parameters=[USER_ADDRESS_CONTEXT],
    )
    context = {
        USER_ADDRESS_CONTEXT: {"address": account},
        ":balanceContextVar": balance,
    }
    condition_result, call_result = rpc_condition.verify(
        providers=condition_providers, **context
    )
    assert condition_result is True
    assert call_result == balance

    # modify balance to make it false
    invalid_balance = balance + 1
    context[":balanceContextVar"] = invalid_balance
    condition_result, call_result = rpc_condition.verify(
        providers={testerchain.client.chain_id: [testerchain.provider]}, **context
    )
    assert condition_result is False
    assert call_result != invalid_balance


@mock.patch(
    "nucypher.policy.conditions.evm.get_context_value",
    side_effect=_dont_validate_user_address,
)
def test_erc20_evm_condition_evaluation(
    get_context_value_mock, testerchain, erc20_evm_condition_balanceof, condition_providers
):
    context = {USER_ADDRESS_CONTEXT: {"address": testerchain.unassigned_accounts[0]}}
    condition_result, call_result = erc20_evm_condition_balanceof.verify(
        providers=condition_providers, **context
    )
    assert condition_result is True

    context[USER_ADDRESS_CONTEXT]["address"] = testerchain.etherbase_account
    condition_result, call_result = erc20_evm_condition_balanceof.verify(
        providers=condition_providers, **context
    )
    assert condition_result is False


def test_erc20_evm_condition_evaluation_with_custom_context_variable(
    testerchain, custom_context_variable_erc20_condition, condition_providers
):
    context = {":addressToUse": testerchain.unassigned_accounts[0]}
    condition_result, call_result = custom_context_variable_erc20_condition.verify(
        providers=condition_providers, **context
    )
    assert condition_result is True

    context[":addressToUse"] = testerchain.etherbase_account
    condition_result, call_result = custom_context_variable_erc20_condition.verify(
        providers=condition_providers, **context
    )
    assert condition_result is False


@mock.patch(
    "nucypher.policy.conditions.evm.get_context_value",
    side_effect=_dont_validate_user_address,
)
def test_erc721_evm_condition_owner_evaluation(
    get_context_value_mock, testerchain, test_registry, erc721_evm_condition_owner, condition_providers
):
    account, *other_accounts = testerchain.client.accounts
    # valid owner of nft
    context = {
        USER_ADDRESS_CONTEXT: {"address": account},
        ":tokenId": 1,  # valid token id
    }
    condition_result, call_result = erc721_evm_condition_owner.verify(
        providers=condition_providers, **context
    )
    assert condition_result is True
    assert call_result == account

    # invalid token id
    with pytest.raises(RPCExecutionFailed):
        context[":tokenId"] = 255
        _, _ = erc721_evm_condition_owner.verify(
            providers=condition_providers, **context
        )

    # invalid owner of nft
    other_account = other_accounts[0]
    context = {
        USER_ADDRESS_CONTEXT: {"address": other_account},
        ":tokenId": 1,  # valid token id
    }
    condition_result, call_result = erc721_evm_condition_owner.verify(
        providers=condition_providers, **context
    )
    assert condition_result is False
    assert call_result != other_account


@mock.patch(
    "nucypher.policy.conditions.evm.get_context_value",
    side_effect=_dont_validate_user_address,
)
def test_erc721_evm_condition_balanceof_evaluation(
    get_context_value_mock, testerchain, test_registry, erc721_evm_condition_balanceof, condition_providers
):
    account, *other_accounts = testerchain.client.accounts
    context = {USER_ADDRESS_CONTEXT: {"address": account}}  # owner of NFT
    condition_result, call_result = erc721_evm_condition_balanceof.verify(
        providers=condition_providers, **context
    )
    assert condition_result is True

    # invalid owner of nft
    other_account = other_accounts[0]  # not an owner of NFT
    context = {USER_ADDRESS_CONTEXT: {"address": other_account}}
    condition_result, call_result = erc721_evm_condition_balanceof.verify(
        providers=condition_providers, **context
    )
    assert not condition_result


def test_subscription_manager_is_active_policy_condition_evaluation(
    testerchain,
    enacted_policy,
    subscription_manager_is_active_policy_condition,
    condition_providers
):
    context = {":hrac": bytes(enacted_policy.hrac)}  # user-defined context var
    (
        condition_result,
        call_result,
    ) = subscription_manager_is_active_policy_condition.verify(
        providers=condition_providers, **context
    )
    assert call_result
    assert condition_result is True

    # non-active policy hrac
    context[":hrac"] = os.urandom(16)
    condition_result, call_result = subscription_manager_is_active_policy_condition.verify(
        providers=condition_providers, **context
    )
    assert not call_result
    assert not condition_result


def test_subscription_manager_get_policy_policy_struct_condition_evaluation_struct_direct_value(
    testerchain, test_registry, enacted_policy, condition_providers
):
    # zeroized policy struct - specificed as list
    zeroized_policy_struct = [
        NULL_ADDRESS,
        0,
        0,
        0,
        NULL_ADDRESS,
    ]

    subscription_manager = ContractAgency.get_agent(
        SubscriptionManagerAgent,
        registry=test_registry,
        blockchain_endpoint=TEST_ETH_PROVIDER_URI,
    )
    condition = ContractCondition(
        contract_address=subscription_manager.contract.address,
        function_abi=subscription_manager.contract.get_function_by_name(
            "getPolicy"
        ).abi,
        method="getPolicy",
        chain=TESTERCHAIN_CHAIN_ID,
        return_value_test=ReturnValueTest("==", zeroized_policy_struct),
        parameters=[":hrac"],
    )

    context = {
        ":hrac": bytes(enacted_policy.hrac),
    }  # user-defined context vars
    condition_result, call_result = condition.verify(
        providers=condition_providers, **context
    )
    assert not condition_result  # not zeroized policy

    # unknown policy hrac
    context[":hrac"] = os.urandom(16)
    condition_result, call_result = condition.verify(
        providers=condition_providers, **context
    )
    assert condition_result is True  # zeroized policy was indeed returned


def test_subscription_manager_get_policy_policy_struct_condition_evaluation_context_var(
    testerchain,
    enacted_policy,
    subscription_manager_get_policy_zeroized_policy_struct_condition,
    condition_providers
):
    # zeroized policy struct
    zeroized_policy_struct = (
        NULL_ADDRESS, 0, 0, 0, NULL_ADDRESS,
    )
    context = {
        ":hrac": bytes(enacted_policy.hrac),
        ":expectedPolicyStruct": zeroized_policy_struct,
    }  # user-defined context vars
    condition_result, call_result = subscription_manager_get_policy_zeroized_policy_struct_condition.verify(
        providers=condition_providers, **context
    )
    assert call_result != zeroized_policy_struct
    assert not condition_result  # not zeroized policy

    # unknown policy hrac
    context[":hrac"] = os.urandom(16)
    condition_result, call_result = subscription_manager_get_policy_zeroized_policy_struct_condition.verify(
        providers=condition_providers, **context
    )
    assert call_result == zeroized_policy_struct
    assert condition_result is True  # zeroized policy was indeed returned


def test_subscription_manager_get_policy_policy_struct_condition_key_tuple_evaluation(
    testerchain,
    test_registry,
    idle_policy,
    enacted_policy,
    condition_providers,
):
    # enacted policy created from idle policy
    size = len(idle_policy.kfrags)
    start = idle_policy.commencement
    end = idle_policy.expiration
    sponsor = idle_policy.publisher.checksum_address

    context = {
        ":hrac": bytes(enacted_policy.hrac),
    }  # user-defined context vars
    subscription_manager = ContractAgency.get_agent(
        SubscriptionManagerAgent,
        registry=test_registry,
        blockchain_endpoint=TEST_ETH_PROVIDER_URI,
    )

    # test "sponsor" key (owner is the same as sponsor for this policy)
    condition = ContractCondition(
        contract_address=subscription_manager.contract.address,
        function_abi=subscription_manager.contract.get_function_by_name(
            "getPolicy"
        ).abi,
        method="getPolicy",
        chain=TESTERCHAIN_CHAIN_ID,
        return_value_test=ReturnValueTest(comparator="==", value=sponsor, index=0),
        parameters=[":hrac"],
    )
    condition_result, _ = condition.verify(providers=condition_providers, **context)
    assert condition_result

    # test "sponsor" key not equal to correct value
    condition = ContractCondition(
        contract_address=subscription_manager.contract.address,
        function_abi=subscription_manager.contract.get_function_by_name(
            "getPolicy"
        ).abi,
        method="getPolicy",
        chain=TESTERCHAIN_CHAIN_ID,
        return_value_test=ReturnValueTest(comparator="!=", value=sponsor, index=0),
        parameters=[":hrac"],
    )
    condition_result, _ = condition.verify(providers=condition_providers, **context)
    assert not condition_result

    # test "start" key
    condition = ContractCondition(
        contract_address=subscription_manager.contract.address,
        function_abi=subscription_manager.contract.get_function_by_name(
            "getPolicy"
        ).abi,
        method="getPolicy",
        chain=TESTERCHAIN_CHAIN_ID,
        return_value_test=ReturnValueTest(comparator="==", value=start, index=1),
        parameters=[":hrac"],
    )
    condition_result, _ = condition.verify(providers=condition_providers, **context)
    assert condition_result

    # test "start" key not equal to correct value
    condition = ContractCondition(
        contract_address=subscription_manager.contract.address,
        function_abi=subscription_manager.contract.get_function_by_name(
            "getPolicy"
        ).abi,
        method="getPolicy",
        chain=TESTERCHAIN_CHAIN_ID,
        return_value_test=ReturnValueTest(comparator="!=", value=start, index=1),
        parameters=[":hrac"],
    )
    condition_result, _ = condition.verify(providers=condition_providers, **context)
    assert not condition_result

    # test "end" index
    condition = ContractCondition(
        contract_address=subscription_manager.contract.address,
        function_abi=subscription_manager.contract.get_function_by_name(
            "getPolicy"
        ).abi,
        method="getPolicy",
        chain=TESTERCHAIN_CHAIN_ID,
        return_value_test=ReturnValueTest(comparator="==", value=end, index=2),
        parameters=[":hrac"],
    )
    condition_result, _ = condition.verify(providers=condition_providers, **context)
    assert condition_result

    # test "size" index
    condition = ContractCondition(
        contract_address=subscription_manager.contract.address,
        function_abi=subscription_manager.contract.get_function_by_name(
            "getPolicy"
        ).abi,
        method="getPolicy",
        chain=TESTERCHAIN_CHAIN_ID,
        return_value_test=ReturnValueTest(comparator="==", value=size, index=3),
        parameters=[":hrac"],
    )
    condition_result, _ = condition.verify(providers=condition_providers, **context)
    assert condition_result

    # test "owner" index (owner is sponsor, so owner is set to null address)
    condition = ContractCondition(
        contract_address=subscription_manager.contract.address,
        function_abi=subscription_manager.contract.get_function_by_name(
            "getPolicy"
        ).abi,
        method="getPolicy",
        chain=TESTERCHAIN_CHAIN_ID,
        return_value_test=ReturnValueTest(comparator="==", value=NULL_ADDRESS, index=4),
        parameters=[":hrac"],
    )
    condition_result, _ = condition.verify(providers=condition_providers, **context)
    assert condition_result


def test_subscription_manager_get_policy_policy_struct_condition_index_and_value_context_var_evaluation(
    testerchain,
    test_registry,
    idle_policy,
    enacted_policy,
    condition_providers,
):
    # enacted policy created from idle policy
    sponsor = idle_policy.publisher.checksum_address
    context = {
        ":hrac": bytes(enacted_policy.hrac),
        ":sponsor": sponsor,
    }  # user-defined context vars
    subscription_manager = ContractAgency.get_agent(
        SubscriptionManagerAgent,
        registry=test_registry,
        blockchain_endpoint=TEST_POLYGON_PROVIDER_URI,
    )

    # test "sponsor" index not equal to correct value
    condition = ContractCondition(
        contract_address=subscription_manager.contract.address,
        function_abi=subscription_manager.contract.get_function_by_name(
            "getPolicy"
        ).abi,
        method="getPolicy",
        chain=TESTERCHAIN_CHAIN_ID,
        return_value_test=ReturnValueTest(
            comparator="!=",
            value=":sponsor",  # use sponsor sponsor context var
            index=0,
        ),
        parameters=[":hrac"],
    )
    condition_result, _ = condition.verify(providers=condition_providers, **context)
    assert not condition_result


def test_time_condition_evaluation(testerchain, time_condition, condition_providers):
    assert time_condition.timestamp == 0
    condition_result, call_result = time_condition.verify(providers=condition_providers)
    assert condition_result is True


def test_not_time_condition_evaluation(
    testerchain, time_condition, condition_providers
):
    not_condition = NotCompoundCondition(operand=time_condition)
    condition_result, call_value = time_condition.verify(providers=condition_providers)
    assert condition_result is True

    not_condition_result, not_call_value = not_condition.verify(
        providers=condition_providers
    )
    assert not_condition_result is (not condition_result)
    assert not_call_value == call_value


def test_simple_compound_conditions_lingo_evaluation(
    testerchain, compound_blocktime_lingo, condition_providers
):
    conditions = json.dumps(compound_blocktime_lingo)
    lingo = ConditionLingo.from_json(conditions)
    result = lingo.eval(providers=condition_providers)
    assert result is True


def test_not_of_simple_compound_conditions_lingo_evaluation(
    testerchain, compound_blocktime_lingo, condition_providers
):
    # evaluate base condition
    access_condition_lingo = ConditionLingo.from_dict(compound_blocktime_lingo)
    result = access_condition_lingo.eval(providers=condition_providers)
    assert result is True

    # evaluate not of base condition
    not_access_condition = NotCompoundCondition(
        operand=access_condition_lingo.condition
    )
    not_access_condition_lingo = ConditionLingo(condition=not_access_condition)
    not_result = not_access_condition_lingo.eval(providers=condition_providers)
    assert not_result is False
    assert not_result is (not result)


@mock.patch(
    "nucypher.policy.conditions.evm.get_context_value",
    side_effect=_dont_validate_user_address,
)
def test_onchain_conditions_lingo_evaluation(
    get_context_value_mock,
    testerchain,
    compound_lingo,
    condition_providers,
):
    context = {USER_ADDRESS_CONTEXT: {"address": testerchain.etherbase_account}}
    result = compound_lingo.eval(providers=condition_providers, **context)
    assert result is True


@mock.patch(
    "nucypher.policy.conditions.evm.get_context_value",
    side_effect=_dont_validate_user_address,
)
def test_not_of_onchain_conditions_lingo_evaluation(
    get_context_value_mock,
    testerchain,
    compound_lingo,
    condition_providers,
):
    context = {USER_ADDRESS_CONTEXT: {"address": testerchain.etherbase_account}}
    result = compound_lingo.eval(providers=condition_providers, **context)
    assert result is True

    not_condition = NotCompoundCondition(operand=compound_lingo.condition)
    not_access_condition_lingo = ConditionLingo(condition=not_condition)
    not_result = not_access_condition_lingo.eval(
        providers=condition_providers, **context
    )
    assert not_result is False
    assert not_result is (not result)


def test_single_retrieve_with_onchain_conditions(enacted_policy, bob, ursulas):
    bob.remember_node(ursulas[0])
    bob.start_learning_loop()
    conditions = {
        "version": ConditionLingo.VERSION,
        "condition": {
            "conditionType": ConditionType.COMPOUND.value,
            "operator": "and",
            "operands": [
                {
                    "conditionType": ConditionType.TIME.value,
                    "returnValueTest": {"value": 0, "comparator": ">"},
                    "method": "blocktime",
                    "chain": TESTERCHAIN_CHAIN_ID,
                },
                {
                    "conditionType": ConditionType.RPC.value,
                    "chain": TESTERCHAIN_CHAIN_ID,
                    "method": "eth_getBalance",
                    "parameters": [bob.checksum_address, "latest"],
                    "returnValueTest": {"comparator": ">=", "value": 10000000000000},
                },
            ],
        },
    }
    messages, message_kits = make_message_kits(enacted_policy.public_key, conditions)
    policy_info_kwargs = dict(
        encrypted_treasure_map=enacted_policy.treasure_map,
        alice_verifying_key=enacted_policy.publisher_verifying_key,
    )

    cleartexts = bob.retrieve_and_decrypt(
        message_kits=message_kits,
        **policy_info_kwargs,
    )

    assert cleartexts == messages
