
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
