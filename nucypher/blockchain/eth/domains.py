from enum import Enum
from typing import Any, Dict, NamedTuple, Tuple

from cytoolz.functoolz import memoize


class UnrecognizedTacoDomain(Exception):
    """Raised when a domain is not recognized."""


class ChainInfo(NamedTuple):
    id: int
    name: str


class EthChain(ChainInfo, Enum):
    MAINNET = (1, "mainnet")
    SEPOLIA = (11155111, "sepolia")


class PolygonChain(ChainInfo, Enum):
    MAINNET = (137, "polygon")
    AMOY = (80002, "amoy")


class TACoDomain:
    def __init__(
        self,
        name: str,
        eth_chain: EthChain,
        polygon_chain: PolygonChain,
        condition_chains: Tuple[ChainInfo, ...],
    ):
        self.name = name
        self.eth_chain = eth_chain
        self.polygon_chain = polygon_chain
        self.condition_chains = condition_chains

    def __repr__(self) -> str:
        return f"<TACoDomain {self.name}>"

    def __str__(self) -> str:
        return self.name

    def __hash__(self) -> int:
        return hash(
            (self.name, self.eth_chain, self.polygon_chain, self.condition_chains)
        )

    def __bytes__(self) -> bytes:
        return self.name.encode()

    def __eq__(self, other: Any) -> bool:
        if not isinstance(other, TACoDomain):
            return False
        return (
            self.name == other.name
            and self.eth_chain == other.eth_chain
            and self.polygon_chain == other.polygon_chain
            and self.condition_chains == other.condition_chains
        )

    def __bool__(self) -> bool:
        return True

    @property
    def is_testnet(self) -> bool:
        return self.eth_chain != EthChain.MAINNET

    @property
    def condition_chain_ids(self) -> set:
        return set(chain.id for chain in self.condition_chains)



MAINNET = TACoDomain(
    name="mainnet",
    eth_chain=EthChain.MAINNET,
    polygon_chain=PolygonChain.MAINNET,
    condition_chains=(EthChain.MAINNET, PolygonChain.MAINNET),
)

LYNX = TACoDomain(
    name="lynx",
    eth_chain=EthChain.SEPOLIA,
    polygon_chain=PolygonChain.AMOY,
    condition_chains=(
        EthChain.MAINNET,
        EthChain.SEPOLIA,
        PolygonChain.AMOY,
        PolygonChain.MAINNET,
    ),
)

TAPIR = TACoDomain(
    name="tapir",
    eth_chain=EthChain.SEPOLIA,
    polygon_chain=PolygonChain.AMOY,
    condition_chains=(EthChain.SEPOLIA, PolygonChain.AMOY),
)


DEFAULT_DOMAIN: TACoDomain = MAINNET

SUPPORTED_DOMAINS: Dict[str, TACoDomain] = {
    str(domain): domain for domain in (MAINNET, LYNX, TAPIR)
}


@memoize
def get_domain(d: Any) -> TACoDomain:
    if not isinstance(d, str):
        raise TypeError(f"domain must be a string, not {type(d)}")
    for name, domain in SUPPORTED_DOMAINS.items():
        if name == d == str(domain):
            return domain
    raise UnrecognizedTacoDomain(f"{d} is not a recognized domain.")
