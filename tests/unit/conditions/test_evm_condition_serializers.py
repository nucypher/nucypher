import json

from nucypher.policy.conditions._utils import _deserialize_condition_lingo
from nucypher.policy.conditions.evm import ContractCondition
from nucypher.policy.conditions.lingo import ConditionLingo


def test_evm_condition_json_serializers(ERC1155_balance_condition_data):
    original_data = ERC1155_balance_condition_data
    condition = ContractCondition.from_json(original_data)
    serialized_data = condition.to_json()
    # assert json.loads(original_data) == json.loads(serialized_data)


def test_type_resolution_from_json(timelock_condition, rpc_condition, evm_condition):
    conditions = (
        timelock_condition,
        rpc_condition,
        evm_condition
    )
    for condition in conditions:
        condition_json = condition.to_json()
        resolved_condition = _deserialize_condition_lingo(condition_json)
        assert isinstance(resolved_condition, type(condition))


def test_conditions_lingo_serialization(timelock_condition, rpc_condition, evm_condition, lingo):
    json_serialized_lingo = json.dumps([l.to_dict() for l in lingo.lingo])
    lingo_json = lingo.to_json()
    restored_lingo = ConditionLingo.from_json(data=lingo_json)
    assert lingo_json == json_serialized_lingo
    restored_lingo_json = restored_lingo.to_json()
    assert restored_lingo_json == json_serialized_lingo

    lingo_b64 = restored_lingo.to_base64()
    restored_lingo = ConditionLingo.from_base64(lingo_b64)

    lingo_bytes = bytes(restored_lingo)
    restored_lingo = ConditionLingo.from_bytes(lingo_bytes)

    # after all the serialization and transformation the content must remain identical
    assert restored_lingo.to_json() == lingo_json
