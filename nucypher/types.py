from typing import NewType, TypeVar

ERC20UNits = NewType("ERC20UNits", int)
NuNits = NewType("NuNits", ERC20UNits)
TuNits = NewType("TuNits", ERC20UNits)

Agent = TypeVar("Agent", bound="agents.EthereumContractAgent")  # noqa: F821

RitualId = int
PhaseId = int
