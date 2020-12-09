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
from typing import Dict, Optional, List

from nucypher.blockchain.eth.sol.compile.config import OPTIMIZER_RUNS
from nucypher.blockchain.eth.sol.compile.constants import SOLC_LOGGER
from nucypher.blockchain.eth.sol.compile.exceptions import CompilationError
from nucypher.blockchain.eth.sol.compile.types import VersionString
from nucypher.exceptions import DevelopmentInstallationRequired


def __execute(compiler_version: VersionString, input_config: Dict, allow_paths: Optional[List[str]]):
    """Executes the solcx command and underlying solc wrapper"""

    # Lazy import to allow for optional installation of solcx
    try:
        from solcx.install import get_executable
        from solcx.main import compile_standard
    except ImportError:
        raise DevelopmentInstallationRequired(importable_name='solcx')

    # Prepare Solc Command
    solc_binary_path: Path = get_executable(version=compiler_version)

    _allow_paths = ',' + ','.join(str(p) for p in allow_paths)

    # Execute Compilation
    try:
        compiler_output = compile_standard(input_data=input_config,
                                           allow_paths=_allow_paths,
                                           solc_binary=solc_binary_path)
    except FileNotFoundError:
        raise CompilationError("The solidity compiler is not at the specified path. "
                               "Check that the file exists and is executable.")
    except PermissionError:
        raise CompilationError(f"The solidity compiler binary at {solc_binary_path} is not executable. "
                               "Check the file's permissions.")

    errors = compiler_output.get('errors')
    if errors:
        formatted = '\n'.join([error['formattedMessage'] for error in errors])
        SOLC_LOGGER.warn(f"Errors during compilation: \n{formatted}")

    SOLC_LOGGER.info(f"Successfully compiled {len(compiler_output)} sources with {OPTIMIZER_RUNS} optimization runs")
    return compiler_output
