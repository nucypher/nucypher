from pathlib import Path

from constant_sorrow.constants import NO_BLOCKCHAIN_CONNECTION

# TODO: Move to constants.py?
BASE_DIRECTORY = Path(__file__).parent
CONTRACT_REGISTRY_BASE = BASE_DIRECTORY / "contract_registry"


NO_BLOCKCHAIN_CONNECTION.bool_value(False)
