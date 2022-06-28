import json
from pathlib import Path

import pytest

VECTORS_FILE = Path(__file__).parent / "vectors.json"

with open(VECTORS_FILE, 'r') as file:
    VECTORS = json.loads(file.read())


@pytest.fixture()
def ERC1155_balance_condition():
    return VECTORS['ERC1155_balance']
