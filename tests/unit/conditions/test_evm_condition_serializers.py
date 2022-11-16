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

import json

from nucypher.policy.conditions._utils import _deserialize_condition_lingo
from nucypher.policy.conditions.evm import ContractCondition
from nucypher.policy.conditions.lingo import ConditionLingo


def test_condition_bug(condition_bug_data):
    original_data = condition_bug_data
    condition = ContractCondition.from_json(original_data)
    serialized_data = condition.to_json()
    deserialized_data = json.loads(serialized_data)
    assert json.loads(original_data) == deserialized_data


def test_replicate_porter(condition_bug_data):
    """Porter deserializes conditions, then serializes again for sending to Ursula.
    Here we check that the end condition are identical to the original condition.
    """
    original_data = condition_bug_data
    first_condition = ContractCondition.from_json(original_data)
    serialized_data = first_condition.to_json()
    second_condition = ContractCondition.from_json(serialized_data)
    final_data = second_condition.to_json()
    assert original_data == final_data

def test_evm_condition_function_abi(t_staking_data):
    original_data = t_staking_data
    condition = ContractCondition.from_json(original_data)
    serialized_data = condition.to_json()

    deserialized_data = json.loads(serialized_data)
    assert deserialized_data["functionAbi"] == condition.function_abi


def test_evm_condition_json_serializers(ERC1155_balance_condition_data):
    original_data = ERC1155_balance_condition_data
    condition = ContractCondition.from_json(original_data)
    serialized_data = condition.to_json()

    deserialized_data = json.loads(serialized_data)

    assert json.loads(original_data) == deserialized_data


def test_type_resolution_from_json(
    timelock_condition, rpc_condition, erc20_evm_condition, erc721_evm_condition
):
    conditions = (
        timelock_condition,
        rpc_condition,
        erc20_evm_condition,
        erc721_evm_condition,
    )
    for condition in conditions:
        condition_json = condition.to_json()
        resolved_condition = _deserialize_condition_lingo(condition_json)
        assert isinstance(resolved_condition, type(condition))


def test_conditions_lingo_serialization(lingo):
    json_serialized_lingo = json.dumps([l.to_dict() for l in lingo.conditions])
    lingo_json = lingo.to_json()
    restored_lingo = ConditionLingo.from_json(data=lingo_json)
    assert lingo_json == json_serialized_lingo
    restored_lingo_json = restored_lingo.to_json()
    assert restored_lingo_json == json_serialized_lingo

    lingo_b64 = restored_lingo.to_base64()
    restored_lingo = ConditionLingo.from_base64(lingo_b64)

    # after all the serialization and transformation the content must remain identical
    assert restored_lingo.to_json() == lingo_json
