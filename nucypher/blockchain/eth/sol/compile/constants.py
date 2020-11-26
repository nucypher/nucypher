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

# Do not compile contracts containing...
IGNORE_CONTRACT_PREFIXES: Tuple[str, ...] = (
    'Abstract',
    'Interface'
)

DEFAULT_VERSION_STRING: str = 'v0.0.0'  # for both compiler and devdoc versions (must fully match regex pattern below)
