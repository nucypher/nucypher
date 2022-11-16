

import json
from pathlib import Path

STANDARD_ABIS_FILEPATH = Path(__file__).parent / 'abis.json'
with open(STANDARD_ABIS_FILEPATH, 'r') as file:
    STANDARD_ABIS = json.loads(file.read())

STANDARD_ABI_CONTRACT_TYPES = set(STANDARD_ABIS)
