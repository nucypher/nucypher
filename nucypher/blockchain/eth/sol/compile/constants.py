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

import re

from nucypher.exceptions import DevelopmentInstallationRequired

try:
    import tests
except ImportError:
    raise DevelopmentInstallationRequired(importable_name='tests')

from pathlib import Path
from typing import Tuple, Pattern

from nucypher.blockchain.eth import sol

# Logging
SOLC_LOGGER = Logger("solidity-compilation")

# Vocabulary
CONTRACTS = 'contracts'
ZEPPELIN: str = 'zeppelin'
ARAGON: str = 'aragon'

# Base Paths
SOLIDITY_SOURCE_ROOT: Path = Path(sol.__file__).parent / 'source'
TEST_SOLIDITY_SOURCE_ROOT: Path = Path(tests.__file__).parent / CONTRACTS / CONTRACTS

# Import Remapping
ZEPPELIN_DIR: Path = SOLIDITY_SOURCE_ROOT / ZEPPELIN
ARAGON_DIR: Path = SOLIDITY_SOURCE_ROOT / ARAGON
NUCYPHER_CONTRACTS_DIR: Path = SOLIDITY_SOURCE_ROOT / 'contracts'

# Do not compile contracts containing...
IGNORE_CONTRACT_PREFIXES: Tuple[str, ...] = (
    'Abstract',
    'Interface'
)

DEFAULT_VERSION_STRING: str = 'v0.0.0'  # for both compiler and devdoc versions (must fully match regex pattern below)


# RE pattern for matching solidity source compile version specification in devdoc details.
DEVDOC_VERSION_PATTERN: Pattern = re.compile(r"""
\A            # Anchor must be first
\|            # Anchored pipe literal at beginning of version definition
(             # Start Inner capture group
v             # Capture version starting from symbol v
\d+           # At least one digit of major version
\.            # Digits splitter
\d+           # At least one digit of minor version
\.            # Digits splitter
\d+           # At least one digit of patch
)             # End of capturing
\|            # Anchored end of version definition | 
\Z            # Anchor must be the end of the match
""", re.VERBOSE)
