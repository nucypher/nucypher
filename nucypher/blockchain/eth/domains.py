from enum import Enum
from typing import NamedTuple


class ChainInfo(NamedTuple):
    id: int
    name: str


class EthChain(ChainInfo, Enum):
    MAINNET = (1, "mainnet")
    GOERLI = (5, "goerli")
    SEPOLIA = (11155111, "sepolia")


class PolygonChain(ChainInfo, Enum):
    MAINNET = (137, "polygon")
    MUMBAI = (80001, "mumbai")


class TACoDomain:

    def __init__(self,
        name: str,
        eth_chain: EthChain,
        polygon_chain: PolygonChain,
    ):
        self.name = name
        self.eth_chain = eth_chain
        self.polygon_chain = polygon_chain

    def __repr__(self):
        return f"<TACoDomain {self.name}>"

    def __str__(self):
        return self.name

    def __hash__(self):
        return hash(self.name)

    def __bytes__(self):
        return self.name.encode()

    def __eq__(self, other):
        try:
            return self.name == other.name
        except AttributeError:
            raise TypeError(f"Cannot compare TACoDomain to {type(other)}")

    def __bool__(self):
        return True

    def __iter__(self):
        return str(self)

    @property
    def is_testnet(self) -> bool:
        return self.eth_chain != EthChain.MAINNET



MAINNET = TACoDomain(
    name="mainnet",
    eth_chain=EthChain.MAINNET,
    polygon_chain=PolygonChain.MAINNET,
)

LYNX = TACoDomain(
    name="lynx",
    eth_chain=EthChain.GOERLI,
    polygon_chain=PolygonChain.MUMBAI,
)

TAPIR = TACoDomain(
    name="tapir",
    eth_chain=EthChain.SEPOLIA,
    polygon_chain=PolygonChain.MUMBAI,
)

DEFAULT_DOMAIN_NAME: str = MAINNET.name

SUPPORTED_DOMAINS = [
    MAINNET,
    LYNX,
    TAPIR,
]

SUPPORTED_DOMAIN_NAMES = [str(domain) for domain in SUPPORTED_DOMAINS]

class Unrecognized(Exception):
    pass

def get_domain(domain: str) -> TACoDomain:
    if not isinstance(domain, str):
        raise TypeError(f"domain must be a string, not {type(domain)}")
    for taco_domain in SUPPORTED_DOMAINS:
        if taco_domain.name == domain:
            return taco_domain
    raise Unrecognized(f"{domain} is not a recognized domain.")
