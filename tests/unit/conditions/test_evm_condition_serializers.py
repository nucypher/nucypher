import json

from nucypher.policy.conditions import EVMCondition


def test_evm_condition_json_serializers(ERC1155_balance_condition_data):
    original_data = ERC1155_balance_condition_data
    condition = EVMCondition.from_json(original_data)
    serialized_data = condition.to_json()
    assert json.loads(original_data) == json.loads(serialized_data)
