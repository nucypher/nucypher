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


import itertools

from typing import Tuple, List, Dict

from cytoolz.dicttoolz import merge, merge_with
from pathlib import Path

from blockchain.eth.sol.__conf__ import SOLIDITY_COMPILER_VERSION
from blockchain.eth.sol.compile.aggregation import merge_contract_outputs
from blockchain.eth.sol.compile.collect import collect_sources
from blockchain.eth.sol.compile.config import BASE_COMPILER_CONFIGURATION
from blockchain.eth.sol.compile.config import ALLOWED_PATHS
from blockchain.eth.sol.compile.solc import __execute
from blockchain.eth.sol.compile.types import VersionString, VersionedContractOutputs, CompiledContractOutputs


def compile_sources(solidity_source_dir: Path, version_check: bool = True) -> Dict:
    """Compiled solidity contracts for a single source directory"""
    sources = collect_sources(source_dir=solidity_source_dir)
    solc_configuration = merge(BASE_COMPILER_CONFIGURATION, dict(sources=sources))  # do not mutate
    allowed_paths = ','.join(list(set(str(p) for p in ALLOWED_PATHS)))  # unique
    ignore_version_check: bool = not version_check
    version: VersionString = VersionString(SOLIDITY_COMPILER_VERSION) if ignore_version_check else None
    compiler_output = __execute(compiler_version=version, input_config=solc_configuration, allowed_paths=allowed_paths)
    return compiler_output


def multiversion_compile(solidity_source_dirs: Tuple[Path, ...], compiler_version_check: bool = True) -> VersionedContractOutputs:
    """Compile contracts from `source_dirs` and aggregate the resulting source contract outputs by version"""
    raw_compiler_results: List[CompiledContractOutputs] = list()
    for source_dir in solidity_source_dirs:
        compile_result = compile_sources(solidity_source_dir=source_dir, version_check=compiler_version_check)
        raw_compiler_results.append(compile_result['contracts'])
    raw_compiled_contracts = itertools.chain.from_iterable(output.values() for output in raw_compiler_results)
    versioned_contract_outputs = merge_with(merge_contract_outputs, *raw_compiled_contracts)
    return VersionedContractOutputs(versioned_contract_outputs)
