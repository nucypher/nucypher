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

from typing import Dict, Optional

from nucypher.blockchain.eth.sol.compile.config import OPTIMIZER_RUNS
from nucypher.blockchain.eth.sol.compile.constants import SOLC_LOGGER
from nucypher.blockchain.eth.sol.compile.exceptions import CompilationError
from nucypher.blockchain.eth.sol.compile.types import VersionString
from nucypher.exceptions import DevelopmentInstallationRequired


def __execute(compiler_version: VersionString,
              input_config: Dict,
              allowed_paths: Optional[str] = None,
              base_path: str = None):
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
    SOLC_LOGGER.info(f"Compiling with base path")  # TODO: Add base path

    # Execute Compilation
    try:
        compiler_output = compile_standard(input_data=input_config, base_path=base_path)
    except FileNotFoundError:
        raise CompilationError("The solidity compiler is not at the specified path. "
                               "Check that the file exists and is executable.")
    except PermissionError:
        raise CompilationError(f"The solidity compiler binary at {solc_binary_path} is not executable. "
                               "Check the file's permissions.")
    log.info(f"Successfully compiled {len(compiler_output)} sources with {OPTIMIZER_RUNS} optimization runs")
    return compiler_output
