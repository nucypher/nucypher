import json
from enum import Enum
from typing import NamedTuple, NewType, Optional, TypeVar

from hexbytes import HexBytes

from nucypher.policy.conditions.types import ContextDict
from typing import NamedTuple, NewType, TypeVar

ERC20Units = NewType("ERC20Units", int)
NuNits = NewType("NuNits", ERC20Units)
TuNits = NewType("TuNits", ERC20Units)

Agent = TypeVar("Agent", bound="agents.EthereumContractAgent")  # noqa: F821

RitualId = int
PhaseNumber = int


class PhaseId(NamedTuple):
    ritual_id: RitualId
    phase: PhaseNumber
