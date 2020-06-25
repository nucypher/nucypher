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
from typing import Dict, List, Union, NewType, NamedTuple, Tuple, Optional


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


class SourceBundle(NamedTuple):
    base_path: Path
    other_paths: Tuple[Path, ...] = tuple()
