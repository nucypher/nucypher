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


import os
import re
from pathlib import Path
from twisted.logger import Logger
from typing import Dict, Iterator, List, Optional, Pattern, Tuple, TypeVar, Union

from nucypher.blockchain.eth.sol import SOLIDITY_COMPILER_VERSION as SOURCE_VERSION
from nucypher.exceptions import DevelopmentInstallationRequired

LOG: Logger = Logger('solidity-compiler')


#
# Types
#

# TODO: Is there a better way to specify complex dictionaries with variable keys?
CompiledContracts = TypeVar('CompiledContracts', bound=Dict[str, Dict[str, List[Dict[str, Union[str, List[Dict[str, str]]]]]]])


class CompilerConfiguration(Dict):
    language: str
    sources: Dict[str, Dict[str, str]]
    settings: Dict


#
# Exceptions
#

class CompilationError(RuntimeError):
    """
    Raised when there is a problem compiling nucypher contracts
    or with the expected compiler configuration.
    """


#
# Compiler Constants
#


DEFAULT_CONTRACT_VERSION: str = 'v0.0.0'
SOURCE_ROOT: Path = Path(__file__).parent / 'source'

CONTRACTS: str = 'contracts'
NUCYPHER_CONTRACTS_DIR: Path = SOURCE_ROOT / CONTRACTS

# Third Party Contracts
ZEPPELIN: str = 'zeppelin'
ARAGON: str = 'aragon'
ZEPPELIN_DIR: Path = SOURCE_ROOT / ZEPPELIN
ARAGON_DIR: Path = SOURCE_ROOT / ARAGON


SOURCES: List[str] = [
    str(NUCYPHER_CONTRACTS_DIR.resolve(strict=True))
]

ALLOWED_PATHS: List[str] = [
    str(SOURCE_ROOT.resolve(strict=True))
]

IGNORE_CONTRACT_PREFIXES: Tuple[str, ...] = (
    'Abstract',
    'Interface'
)


# RE pattern for matching solidity source compile version specification in devdoc details.
VERSION_PATTERN: Pattern = re.compile(r"""
(             # Start outer group
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
){1}          # Limit to a single match
""", re.VERBOSE)


#
# Standard "JSON I/O" Compiler Config Reference:
# https://solidity.readthedocs.io/en/latest/using-the-compiler.html#input-description
#
#
# WARNING: Do not change these values unless you know what you are doing.
#

LANGUAGE: str = 'Solidity'
EVM_VERSION: str = 'berlin'
FILE_OUTPUTS: List[str] = []

CONTRACT_OUTPUTS: List[str] = [
    'abi',                     # ABI
    'devdoc',                  # Developer documentation (natspec)
    'userdoc',                 # User documentation (natspec)
    'evm.bytecode.object',     # Bytecode object
]

IMPORT_REMAPPINGS: List[str] = [
    f"{CONTRACTS}={NUCYPHER_CONTRACTS_DIR.resolve()}",
    f"{ZEPPELIN}={ZEPPELIN_DIR.resolve()}",
    f"{ARAGON}={ARAGON_DIR.resolve()}",
]

OPTIMIZER: bool = True
OPTIMIZATION_RUNS: int = 200
OPTIMIZER_SETTINGS = dict(
    enabled=True,
    runs=200
)

COMPILER_SETTINGS: Dict = dict(
    remappings=IMPORT_REMAPPINGS,
    optimizer=OPTIMIZER_SETTINGS,
    evmVersion=EVM_VERSION,
    outputSelection={"*": {"*": CONTRACT_OUTPUTS, "": FILE_OUTPUTS}}  # all contacts(*), all files("")
)


COMPILER_CONFIG = CompilerConfiguration(
    language=LANGUAGE,
    sources=SOURCES,
    settings=COMPILER_SETTINGS
)


#
# Collection
#


def __source_filter(filename: str) -> bool:
    """Helper function for filtering out contracts not intended for compilation"""
    contains_ignored_prefix: bool = any(prefix in filename for prefix in IGNORE_CONTRACT_PREFIXES)
    is_solidity_file: bool = filename.endswith('.sol')
    return is_solidity_file and not contains_ignored_prefix


def __collect_sources(test_contracts: bool,
                      source_dirs: Optional[Path] = None
                      ) -> Dict[str, Dict[str, List[str]]]:

    # Default
    if not source_dirs:
        source_dirs: List[Path] = [SOURCE_ROOT / CONTRACTS]

    # Add test contracts to sources
    if test_contracts:
        from tests.constants import TEST_CONTRACTS_DIR
        source_dirs.append(TEST_CONTRACTS_DIR)

    # Collect all source directories
    source_paths: Dict[str, Dict[str, List[str]]] = dict()
    for source_dir in source_dirs:
        source_walker: Iterator = os.walk(top=str(source_dir), topdown=True)
        # Collect single directory
        for root, dirs, files in source_walker:
            # Collect files in source dir
            for filename in filter(__source_filter, files):
                path = Path(root) / filename
                source_paths[filename] = dict(urls=[str(path.resolve(strict=True))])
                LOG.debug(f"Collecting solidity source {path}")
        LOG.info(f"Collected {len(source_paths)} solidity source files at {source_dir}")
    return source_paths


def __compile(source_dirs: Tuple[Path, ...] = None,
              include_ast: bool = True,
              ignore_version_check: bool = False,
              test_contracts: bool = False) -> dict:
    """Executes the compiler"""

    try:
        # Lazy import to allow for optional installation of solcx
        from solcx.install import get_executable
        from solcx.main import compile_standard
    except ImportError:
        raise DevelopmentInstallationRequired(importable_name='solcx')

    # Solidity Compiler Binary
    compiler_version: str = SOURCE_VERSION if not ignore_version_check else None
    solc_binary_path: str = get_executable(version=compiler_version)

    # Extra compiler options
    if include_ast:
        FILE_OUTPUTS.append('ast')

    # Handle allowed paths
    if test_contracts:
        from tests.constants import TEST_CONTRACTS_DIR
        ALLOWED_PATHS.append(str(TEST_CONTRACTS_DIR.resolve(True)))
    if source_dirs:
        for source in source_dirs:
            ALLOWED_PATHS.append(str(source.resolve(strict=True)))

    # Resolve Sources
    allowed_paths: str = ','.join(ALLOWED_PATHS)
    sources = __collect_sources(source_dirs=source_dirs, test_contracts=test_contracts)
    COMPILER_CONFIG.update(dict(sources=sources))

    LOG.info(f"Compiling with import remappings {' '.join(IMPORT_REMAPPINGS)}")
    try:
        compiled_sol: CompiledContracts = compile_standard(input_data=COMPILER_CONFIG, allow_paths=allowed_paths)
    except FileNotFoundError:
        raise RuntimeError("The solidity compiler is not at the specified path. "
                           "Check that the file exists and is executable.")
    except PermissionError:
        raise RuntimeError(f"The solidity compiler binary at {solc_binary_path} is not executable. "
                           "Check the file's permissions.")
    LOG.info(f"Successfully compiled {len(compiled_sol)} contracts with {OPTIMIZATION_RUNS} optimization runs")
    return compiled_sol


def __extract_version(contract_name: str, contract_data: dict) -> str:

    # Parse
    try:
        devdoc: Dict[str, str] = contract_data['devdoc']
    except KeyError:
        raise CompilationError(f'Solidity compiler did not export devdoc for {contract_name}.')
    try:
        devdoc_details: str = devdoc['details']
    except KeyError:
        LOG.warn(f'No solidity source version specified for {contract_name}')
        return DEFAULT_CONTRACT_VERSION

    # RE
    raw_matches = VERSION_PATTERN.fullmatch(devdoc_details)

    # Positive match(es)
    if raw_matches:
        matches = raw_matches.groups()
        if len(matches) != 1:  # sanity check
            raise CompilationError(f"Multiple version matches in devdoc")
        version = matches[0]   # good match
        return version

    # Negative match: Devdoc included without a version
    else:
        LOG.warn(f'Compiler version not included in devdoc details for {contract_name}')
        return DEFAULT_CONTRACT_VERSION


def __handle_contract(contract_data: dict,
                      ast: bool,
                      source_data,
                      interfaces: dict,
                      exported_name: str,
                      ) -> None:
    if ast:
        # TODO: Sort AST by contract
        ast = source_data['ast']
        contract_data['ast'] = ast
    try:
        existence_data = interfaces[exported_name]
    except KeyError:
        existence_data = dict()
        interfaces.update({exported_name: existence_data})
    version = __extract_version(contract_name=exported_name, contract_data=contract_data)
    if version not in existence_data:
        existence_data.update({version: contract_data})


def compile_nucypher(source_dirs: Optional[Tuple[Path, ...]] = None,
                     include_ast: bool = False,
                     ignore_version_check: bool = False,
                     test_contracts: bool = False
                     ) -> CompiledContracts:
    """Compile nucypher contracts"""

    # Compile
    compile_result = __compile(include_ast=include_ast,
                               ignore_version_check=ignore_version_check,
                               test_contracts=test_contracts,
                               source_dirs=source_dirs)

    # Aggregate
    interfaces = dict()
    compiled_contracts, compiled_sources = compile_result['contracts'].items(), compile_result['sources'].items()
    for (source_path, source_data), (contract_path, compiled_contract) in zip(compiled_sources, compiled_contracts):
        for exported_name, contract_data in compiled_contract.items():
            __handle_contract(ast=include_ast,
                              contract_data=contract_data,
                              source_data=source_data,
                              interfaces=interfaces,
                              exported_name=exported_name)
    return interfaces


# Control export values
__all__ = (
    compile_nucypher,
    DEFAULT_CONTRACT_VERSION
)
