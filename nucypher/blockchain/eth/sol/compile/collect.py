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

from nucypher.blockchain.eth.sol.compile.types import SourceBundle
from nucypher.exceptions import DevelopmentInstallationRequired
try:
    import tests
except ImportError:
    raise DevelopmentInstallationRequired(importable_name='tests')
from nucypher.blockchain.eth.sol.compile.constants import IGNORE_CONTRACT_PREFIXES, SOLC_LOGGER
import os
from pathlib import Path
from typing import Dict, Iterator


def source_filter(filename: str) -> bool:
    """Helper function for filtering out contracts not intended for compilation"""
    contains_ignored_prefix: bool = any(prefix in filename for prefix in IGNORE_CONTRACT_PREFIXES)
    is_solidity_file: bool = filename.endswith('.sol')
    return is_solidity_file and not contains_ignored_prefix


def collect_sources(source_bundle: SourceBundle) -> Dict[str, Path]:
    """
    Combines sources bundle paths. Walks source_dir top-down to the bottom filepath of
    each subdirectory recursively nd filtrates by __source_filter, setting values into `source_paths`.
    """
    source_paths = dict()
    combined_paths = (source_bundle.base_path, *source_bundle.other_paths)
    for source_dir in combined_paths:
        source_walker: Iterator = os.walk(top=source_dir, topdown=True)
        for root, dirs, files in source_walker:            # Collect single directory
            for filename in filter(source_filter, files):  # Collect files in source dir
                path = Path(root) / filename
                if filename in source_paths:
                    raise RuntimeError(f'"{filename}" source is already collected. Verify source bundle filepaths.'
                                       f' Existing {source_paths[filename]}; Duplicate {path}.')
                source_paths[filename] = path
                SOLC_LOGGER.debug(f"Collecting solidity source {path}")
        SOLC_LOGGER.info(f"Collected {len(source_paths)} solidity source files at {source_bundle}")
    return source_paths
