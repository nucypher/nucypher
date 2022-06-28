import json

from nucypher.policy.conditions.evm import EVMCondition


def test_evm_condition_json_serializers(ERC1155_balance_condition):
    original_data = json.dumps(ERC1155_balance_condition)
    condition = EVMCondition.from_json(original_data)
    serialized_data = condition.to_json()
    assert json.loads(original_data) == json.loads(serialized_data)
