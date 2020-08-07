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
from pathlib import Path
from typing import Tuple, List, Dict, Optional

from cytoolz.dicttoolz import merge, merge_with

from nucypher.blockchain.eth.sol.__conf__ import SOLIDITY_COMPILER_VERSION
from nucypher.blockchain.eth.sol.compile.aggregation import merge_contract_outputs
from nucypher.blockchain.eth.sol.compile.collect import collect_sources
from nucypher.blockchain.eth.sol.compile.config import BASE_COMPILER_CONFIGURATION
from nucypher.blockchain.eth.sol.compile.solc import __execute
from nucypher.blockchain.eth.sol.compile.types import (
    VersionString,
    VersionedContractOutputs,
    CompiledContractOutputs,
    SourceBundle
)

CompilerSources = Dict[str, Dict[str, List[str]]]


def prepare_configuration(sources: Dict[str, Path]) -> CompilerSources:
    input_sources = dict()
    for source_name, path in sources.items():
        source_url = path.resolve(strict=True)  # require source path existence
        input_sources[source_name] = dict(urls=[str(source_url)])
    return input_sources


def compile_sources(source_bundle: SourceBundle,
                    version_check: bool = True,
                    allow_paths: Optional[List[str]] = None
                    ) -> Dict:
    """Compiled solidity contracts for a single source directory"""
    sources = collect_sources(source_bundle=source_bundle)
    source_config = prepare_configuration(sources=sources)
    solc_configuration = merge(BASE_COMPILER_CONFIGURATION, dict(sources=source_config))  # does not mutate.
    ignore_version_check: bool = not version_check
    version: VersionString = VersionString(SOLIDITY_COMPILER_VERSION) if ignore_version_check else None
    compiler_output = __execute(compiler_version=version, input_config=solc_configuration, allow_paths=allow_paths)
    return compiler_output


def multiversion_compile(source_bundles: Tuple[SourceBundle, ...],
                         compiler_version_check: bool = True,
                         allow_paths: List[str] = None
                         ) -> VersionedContractOutputs:
    """Compile contracts from `source_dirs` and aggregate the resulting source contract outputs by version"""
    raw_compiler_results: List[CompiledContractOutputs] = list()
    for bundle in source_bundles:
        compile_result = compile_sources(source_bundle=bundle,
                                         version_check=compiler_version_check,
                                         allow_paths=allow_paths)
        raw_compiler_results.append(compile_result['contracts'])
    raw_compiled_contracts = itertools.chain.from_iterable(output.values() for output in raw_compiler_results)
    versioned_contract_outputs = VersionedContractOutputs(merge_with(merge_contract_outputs, *raw_compiled_contracts))
    return versioned_contract_outputs
