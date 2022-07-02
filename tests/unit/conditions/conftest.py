import json
from pathlib import Path

import pytest

from nucypher.policy.conditions import EVMCondition

VECTORS_FILE = Path(__file__).parent / "vectors.json"

with open(VECTORS_FILE, 'r') as file:
    VECTORS = json.loads(file.read())


@pytest.fixture()
def ERC1155_balance_condition_data():
    data = json.dumps(VECTORS['ERC1155_balance'])
    return data


@pytest.fixture()
def ERC1155_balance_condition(ERC1155_balance_condition_data):
    data = ERC1155_balance_condition_data
    condition = EVMCondition.from_json(data)
    return condition
