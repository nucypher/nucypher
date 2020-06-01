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

from typing import Dict

from blockchain.eth.sol.compile.config import IMPORT_REMAPPING, OPTIMIZER_RUNS, ALLOWED_PATHS
from blockchain.eth.sol.compile.constants import SOLC_LOGGER
from blockchain.eth.sol.compile.exceptions import CompilationError
from blockchain.eth.sol.compile.types import VersionString
from exceptions import DevelopmentInstallationRequired


def __execute(compiler_version: VersionString, input_config: Dict, allowed_paths: str):
    """Executes the solcx command and underlying solc wrapper"""
    log = Logger('execute-solcx')

    # Lazy import to allow for optional installation of solcx
    try:
        from solcx.install import get_executable
        from solcx.main import compile_standard
    except ImportError:
        raise DevelopmentInstallationRequired(importable_name='solcx')

    # Prepare Solc Command
    solc_binary_path: str = get_executable(version=compiler_version)
    SOLC_LOGGER.info(f"Compiling with import remappings {' '.join(IMPORT_REMAPPING)} and allowed paths {ALLOWED_PATHS}")

    # Execute Compilation
    try:
        compiler_output = compile_standard(input_data=input_config, allow_paths=allowed_paths)
    except FileNotFoundError:
        raise CompilationError("The solidity compiler is not at the specified path. "
                               "Check that the file exists and is executable.")
    except PermissionError:
        raise CompilationError(f"The solidity compiler binary at {solc_binary_path} is not executable. "
                               "Check the file's permissions.")
    log.info(f"Successfully compiled {len(compiler_output)} sources with {OPTIMIZER_RUNS} optimization runs")
    return compiler_output
