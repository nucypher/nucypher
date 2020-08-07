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

from logging import Logger
from pathlib import Path
from typing import Tuple

import tests
from nucypher.config.constants import NUCYPHER_TEST_DIR

# Logging
SOLC_LOGGER = Logger("solidity-compilation")

# Vocabulary
CONTRACTS = 'contracts'

TEST_SOLIDITY_SOURCE_ROOT: Path = Path(NUCYPHER_TEST_DIR).parent / CONTRACTS / CONTRACTS

from nucypher.blockchain.eth import sol
SOLIDITY_SOURCE_ROOT: Path = Path(sol.__file__).parent / 'source'
CONTRACT_SOURCE_ROOT = SOLIDITY_SOURCE_ROOT / CONTRACTS
ZEPPELIN_ROOT = SOLIDITY_SOURCE_ROOT / 'zeppelin'
ARAGON_ROOT = SOLIDITY_SOURCE_ROOT / 'aragon'

# Do not compile contracts containing...
IGNORE_CONTRACT_PREFIXES: Tuple[str, ...] = (
    'Abstract',
    'Interface'
)

DEFAULT_VERSION_STRING: str = 'v0.0.0'  # for both compiler and devdoc versions (must fully match regex pattern below)
