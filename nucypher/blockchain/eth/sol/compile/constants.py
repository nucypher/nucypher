

from pathlib import Path
from typing import Tuple
from nucypher.config.constants import NUCYPHER_TEST_DIR

# Logging
from nucypher.utilities.logging import Logger

SOLC_LOGGER = Logger("solidity-compilation")

# Vocabulary
CONTRACTS = 'contracts'

TEST_SOLIDITY_SOURCE_ROOT: Path = Path(NUCYPHER_TEST_DIR) / CONTRACTS / CONTRACTS
TEST_MULTIVERSION_CONTRACTS: Path = Path(NUCYPHER_TEST_DIR) / 'acceptance' / 'blockchain' / 'interfaces' / 'test_contracts' / 'multiversion'

from nucypher.blockchain.eth import sol
SOLIDITY_SOURCE_ROOT: Path = Path(sol.__file__).parent / 'source'
ZEPPELIN = 'zeppelin'
ARAGON = 'aragon'
THRESHOLD = 'threshold'

# Do not compile contracts containing...
IGNORE_CONTRACT_PREFIXES: Tuple[str, ...] = (
    'Abstract',
    'Interface'
)

DEFAULT_VERSION_STRING: str = 'v0.0.0'  # for both compiler and devdoc versions (must fully match regex pattern below)
