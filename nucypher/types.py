from typing import TYPE_CHECKING, NewType, TypeVar

if TYPE_CHECKING:
    from nucypher.blockchain.eth import agents

ERC20UNits = NewType("ERC20UNits", int)
NuNits = NewType("NuNits", ERC20UNits)
TuNits = NewType("TuNits", ERC20UNits)

Agent = TypeVar("Agent", bound="agents.EthereumContractAgent")
