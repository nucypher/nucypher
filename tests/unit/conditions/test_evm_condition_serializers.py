import json

from nucypher.policy.conditions.evm import ContractCondition
from nucypher.policy.conditions.lingo import ConditionLingo
from nucypher.policy.conditions.utils import deserialize_condition_lingo


def test_simple_lingo_serialization(custom_abi_with_multiple_parameters, erc1155_balance_condition_data):
    original_data = custom_abi_with_multiple_parameters
    condition = ContractCondition.from_json(original_data)
    serialized_data = condition.to_json()
    deserialized_data = json.loads(serialized_data)
    assert json.loads(original_data) == deserialized_data

    original_data = erc1155_balance_condition_data
    condition = ContractCondition.from_json(original_data)
    serialized_data = condition.to_json()
    deserialized_data = json.loads(serialized_data)
    assert json.loads(original_data) == deserialized_data


def test_repeating_lingo_serializations(custom_abi_with_multiple_parameters):
    """
    Porter deserializes conditions, then serializes again for sending to Ursula.
    Here we check that the end condition are identical to the original condition.
    """
    original_data = custom_abi_with_multiple_parameters
    first_condition = ContractCondition.from_json(original_data)
    serialized_data = first_condition.to_json()
    second_condition = ContractCondition.from_json(serialized_data)
    final_data = second_condition.to_json()
    assert json.loads(original_data) == json.loads(final_data)


def test_evm_condition_function_abi(t_staking_data):
    original_data = t_staking_data
    condition = ContractCondition.from_json(original_data)
    serialized_data = condition.to_json()
    deserialized_data = json.loads(serialized_data)
    assert deserialized_data["functionAbi"] == condition.function_abi


def test_type_resolution_from_json(
    time_condition, rpc_condition, erc20_evm_condition, erc721_evm_condition
):
    conditions = (time_condition, rpc_condition, erc20_evm_condition)
    for condition in conditions:
        condition_json = condition.to_json()
        resolved_condition = deserialize_condition_lingo(condition_json)
        assert isinstance(resolved_condition, type(condition))


def test_conditions_lingo_serialization(compound_lingo):
    json_serialized_lingo = json.dumps(compound_lingo.condition.to_dict())
    lingo_json = compound_lingo.to_json()
    restored_lingo = ConditionLingo.from_json(data=lingo_json)
    assert lingo_json == json_serialized_lingo
    restored_lingo_json = restored_lingo.to_json()
    assert restored_lingo_json == json_serialized_lingo

    # base64
    lingo_b64 = restored_lingo.to_base64()
    restored_lingo = ConditionLingo.from_base64(lingo_b64)

    # after all the serialization and transformation the content must remain identical
    assert restored_lingo.to_json() == lingo_json


def test_access_control_condition_to_from_bytes(compound_lingo):
    # bytes
    condition_bytes = bytes(compound_lingo.condition)
    condition = compound_lingo.condition.__class__.from_bytes(condition_bytes)
    assert condition.to_json() == compound_lingo.condition.to_json()


def test_access_control_condition_to_from_dict(compound_lingo):
    # dict
    condition_dict = compound_lingo.condition.to_dict()
    condition = compound_lingo.condition.__class__.from_dict(condition_dict)
    assert condition.to_json() == compound_lingo.condition.to_json()
