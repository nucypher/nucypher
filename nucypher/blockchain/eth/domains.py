from enum import Enum
from typing import NamedTuple


class ChainInfo(NamedTuple):
    id: int
    name: str


class EthChain(ChainInfo, Enum):
    MAINNET = ChainInfo(1, "mainnet")
    GOERLI = ChainInfo(5, "goerli")
    SEPOLIA = ChainInfo(11155111, "sepolia")
    TESTERCHAIN = ChainInfo(131277322940537, "eth-tester")


class PolygonChain(ChainInfo, Enum):
    POLYGON = ChainInfo(137, "polygon")
    MUMBAI = ChainInfo(80001, "mumbai")
    TESTERCHAIN = ChainInfo(131277322940537, "eth-tester")


class TACoDomain(NamedTuple):
    name: str
    eth_chain: EthChain
    polygon_chain: PolygonChain

    def is_testnet(self) -> bool:
        return self.eth_chain != EthChain.MAINNET


class UnrecognizedDomain(RuntimeError):
    """Raised when a provided domain name is not recognized."""


MAINNET = TACoDomain("mainnet", EthChain.MAINNET, PolygonChain.POLYGON)
# Testnets
ORYX = TACoDomain("oryx", EthChain.GOERLI, PolygonChain.POLYGON)
LYNX = TACoDomain("lynx", EthChain.GOERLI, PolygonChain.MUMBAI)
TAPIR = TACoDomain("tapir", EthChain.SEPOLIA, PolygonChain.MUMBAI)
IBEX = TACoDomain(
    "ibex", EthChain.GOERLI, None
)  # this is required for configuration file migrations (backwards compatibility)

DEFAULT_DOMAIN_NAME: str = MAINNET.name

SUPPORTED_DOMAINS = [
    MAINNET,
    ORYX,
    LYNX,
    TAPIR,
]

SUPPORTED_DOMAIN_NAMES = [domain.name for domain in SUPPORTED_DOMAINS]


def from_domain_name(domain: str) -> TACoDomain:
    for taco_domain in SUPPORTED_DOMAINS:
        if taco_domain.name == domain:
            return taco_domain

    raise UnrecognizedDomain(f"{domain} is not a recognized domain.")
