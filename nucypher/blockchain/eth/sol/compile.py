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


from nucypher.exceptions import DevelopmentInstallationRequired
try:
    import tests
except ImportError:
    raise DevelopmentInstallationRequired(importable_name='tests')

import itertools
import os
import re
from cytoolz.dicttoolz import merge, merge_with
from pathlib import Path
from twisted.logger import Logger
from typing import Dict, Iterator, List, NewType, Pattern, Tuple, Union

from nucypher.blockchain.eth import sol
from nucypher.blockchain.eth.sol import SOLIDITY_COMPILER_VERSION as SOURCE_VERSION

LOG: Logger = Logger('solidity-compiler')


#
# Types
#


class ABI(Dict):
    inputs: List
    name: str
    outputs: List[Dict[str, str]]
    stateMutability: str
    type: str


class CompiledContractOutputs(Dict):
    abi: ABI
    devdoc: Dict[str, Union[str, Dict[str, str]]]
    evm: Dict[str, Dict]
    userdoc: Dict


VersionString = NewType('VersionString', str)

VersionedContractOutputs = NewType('VersionedContractOutputs', Dict[VersionString, CompiledContractOutputs])


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


class ProgrammingError(RuntimeError):
    """Caused by a human error in code"""

#
# Compiler Constants
#


# Vocabulary
CONTRACTS = 'contracts'
ZEPPELIN: str = 'zeppelin'
ARAGON: str = 'aragon'

# Base Paths
SOLIDITY_SOURCE_ROOT: Path = Path(sol.__file__).parent / 'source'
TEST_SOLIDITY_SOURCE_ROOT: Path = Path(tests.__file__).parent / CONTRACTS / CONTRACTS

# Import Remappings
ZEPPELIN_DIR: Path = SOLIDITY_SOURCE_ROOT / ZEPPELIN
ARAGON_DIR: Path = SOLIDITY_SOURCE_ROOT / ARAGON
NUCYPHER_CONTRACTS_DIR: Path = SOLIDITY_SOURCE_ROOT / 'contracts'
IMPORT_REMAPPINGS: List[str] = [
    f"contracts={NUCYPHER_CONTRACTS_DIR.resolve()}",
    f"{ZEPPELIN}={ZEPPELIN_DIR.resolve()}",
    f"{ARAGON}={ARAGON_DIR.resolve()}",
]

# Hardcoded for added sanity.
# New top-level contract source directories must be listed here.
# Paths can be commented out to prevent default permission.
# In tests, this list can be mutated to temporarily allow compilation
# of source files that are typically not permitted.
ALLOWED_PATHS = [
    SOLIDITY_SOURCE_ROOT,
    TEST_SOLIDITY_SOURCE_ROOT
]

IGNORE_CONTRACT_PREFIXES: Tuple[str, ...] = (
    'Abstract',
    'Interface'
)

DEFAULT_CONTRACT_VERSION: str = 'v0.0.0'

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


BASE_COMPILER_CONFIGURATION = CompilerConfiguration(
    language=LANGUAGE,
    settings=COMPILER_SETTINGS,
)


#
# Collection
#


def source_filter(filename: str) -> bool:
    """Helper function for filtering out contracts not intended for compilation"""
    contains_ignored_prefix: bool = any(prefix in filename for prefix in IGNORE_CONTRACT_PREFIXES)
    is_solidity_file: bool = filename.endswith('.sol')
    return is_solidity_file and not contains_ignored_prefix


def collect_sources(source_dir: Path) -> Dict[str, Dict[str, List[str]]]:
    """
    Returns a compiler-ready mapping of solidity source files in source_dir (recursive)
    Walks source_dir top-down to the bottom filepath of each subdirectory recursively
    and filtrates by __source_filter, setting values into `source_paths`.
    """
    source_paths: Dict[str, Dict[str, List[str]]] = dict()
    source_walker: Iterator = os.walk(top=str(source_dir), topdown=True)
    # Collect single directory
    for root, dirs, files in source_walker:
        # Collect files in source dir
        for filename in filter(source_filter, files):
            path = Path(root) / filename
            source_paths[filename] = dict(urls=[str(path.resolve(strict=True))])
            LOG.debug(f"Collecting solidity source {path}")
    LOG.info(f"Collected {len(source_paths)} solidity source files at {source_dir}")
    return source_paths


#
# Version Aggregation
#


def extract_version(compiled_contract_outputs: dict) -> str:
    # Parse
    try:
        devdoc: Dict[str, str] = compiled_contract_outputs['devdoc']
    except KeyError:
        # Edge Case
        # ---------
        # If this block is reached, the compiler did not produce results for devdoc at all.
        # Ensure 'devdoc' is listed in `CONTRACT_OUTPUTS` and that solc is the latest version.
        raise CompilationError(f'Solidity compiler did not output devdoc.'
                               f'Check the contract output compiler settings.')
    try:
        devdoc_details: str = devdoc['details']
    except KeyError:
        # This is acceptable behaviour, most likely an un-versioned contract
        LOG.debug(f'No solidity source version specified.')
        return DEFAULT_CONTRACT_VERSION

    # RE Full Match
    raw_matches = DEVDOC_VERSION_PATTERN.fullmatch(devdoc_details)

    # Positive match(es)
    if raw_matches:
        matches = raw_matches.groups()
        if len(matches) != 1:  # sanity check
            # Severe Edge Case
            # -----------------
            # "Impossible" situation: If this block is ever reached,
            # the regular expression matching contract versions
            # inside devdoc details matched multiple groups (versions).
            # If you are here, and this exception is raised - do not panic!
            # This most likely means there is a programming error
            # in the `VERSION_PATTERN` regular expression or the surrounding logic.
            raise ProgrammingError(f"Multiple version matches in devdoc")
        version = matches[0]   # good match
        return version
    else:
        # Negative match: Devdoc included without a version
        LOG.debug(f'Contract not versioned.')
        return DEFAULT_CONTRACT_VERSION


def merge_contract_sources(*compiled_sources):
    return merge(*compiled_sources)  # TODO: S


def merge_contract_outputs(*compiled_versions) -> VersionedContractOutputs:
    versioned_outputs = dict()
    for bundle in compiled_versions:
        for contract_outputs in bundle:
            version = extract_version(compiled_contract_outputs=contract_outputs)
            versioned_outputs[version] = contract_outputs
    return VersionedContractOutputs(versioned_outputs)


#
# Compilation
#

def __execute(compiler_version: VersionString, input_config: Dict, allowed_paths: str):
    """Executes the solcx ocmpile command and solc wrapper"""

    # Lazy import to allow for optional installation of solcx
    try:
        from solcx.install import get_executable
        from solcx.main import compile_standard
    except ImportError:
        raise DevelopmentInstallationRequired(importable_name='solcx')

    # Prepare Solc Command
    solc_binary_path: str = get_executable(version=compiler_version)
    LOG.info(f"Compiling with import remappings {' '.join(IMPORT_REMAPPINGS)} and allowed paths {ALLOWED_PATHS}")

    # Execute Compilation
    try:
        compiler_output = compile_standard(input_data=input_config, allow_paths=allowed_paths)
    except FileNotFoundError:
        raise CompilationError("The solidity compiler is not at the specified path. "
                               "Check that the file exists and is executable.")
    except PermissionError:
        raise CompilationError(f"The solidity compiler binary at {solc_binary_path} is not executable. "
                               "Check the file's permissions.")
    LOG.info(f"Successfully compiled {len(compiler_output)} sources with {OPTIMIZATION_RUNS} optimization runs")
    return compiler_output


def compile(source_dir: Path, version_check: bool = True) -> dict:
    """Prepares a configuration for the compiler"""
    sources = collect_sources(source_dir=source_dir)
    solc_configuration = merge(BASE_COMPILER_CONFIGURATION, dict(sources=sources))  # do not mutate
    allowed_paths = ','.join(list(set(str(p) for p in ALLOWED_PATHS)))  # unique
    version: VersionString = VersionString(SOURCE_VERSION) if version_check else None
    compiler_output = __execute(compiler_version=version, input_config=solc_configuration, allowed_paths=allowed_paths)
    return compiler_output


#
# API
#

def multiversion_compile(solidity_source_dirs: Tuple[Path, ...],
                         ignore_compiler_version_check: bool = False,
                         ) -> VersionedContractOutputs:
    """Compile contracts from `source_dirs` and aggregate the resulting source contract outputs by version"""
    raw_compiler_results: List[CompiledContractOutputs] = list()
    for source_dir in solidity_source_dirs:
        compile_result = compile(source_dir=source_dir, version_check=ignore_compiler_version_check)
        raw_compiler_results.append(compile_result['contracts'])
    raw_compiled_contracts = itertools.chain.from_iterable(output.values() for output in raw_compiler_results)
    versioned_contract_outputs = merge_with(merge_contract_outputs, *raw_compiled_contracts)
    return VersionedContractOutputs(versioned_contract_outputs)


# Control export values
__all__ = (
    multiversion_compile,
    DEFAULT_CONTRACT_VERSION
)
