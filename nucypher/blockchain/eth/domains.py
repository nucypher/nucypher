from enum import Enum
from typing import NamedTuple


class ChainInfo(NamedTuple):
    id: int
    name: str


class EthChain(ChainInfo, Enum):
    MAINNET = (1, "mainnet")
    GOERLI = (5, "goerli")
    SEPOLIA = (11155111, "sepolia")
    TESTERCHAIN = (131277322940537, "eth-tester")


class PolygonChain(ChainInfo, Enum):
    POLYGON = (137, "polygon")
    MUMBAI = (80001, "mumbai")
    TESTERCHAIN = (131277322940537, "eth-tester")


class DomainInfo(NamedTuple):
    name: str
    eth_chain: EthChain
    polygon_chain: PolygonChain

    def __str__(self) -> str:
        return self.name

    def __bytes__(self) -> bytes:
        return self.name.encode()

    @property
    def is_testnet(self) -> bool:
        return self.eth_chain != EthChain.MAINNET


class TACoDomain:
    class Unrecognized(RuntimeError):
        """Raised when a provided domain name is not recognized."""

    MAINNET = DomainInfo("mainnet", EthChain.MAINNET, PolygonChain.POLYGON)
    # Testnets
    ORYX = DomainInfo("oryx", EthChain.GOERLI, PolygonChain.POLYGON)
    LYNX = DomainInfo("lynx", EthChain.GOERLI, PolygonChain.MUMBAI)
    TAPIR = DomainInfo("tapir", EthChain.SEPOLIA, PolygonChain.MUMBAI)
    IBEX = DomainInfo(
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

    @classmethod
    def get_domain_info(cls, domain: str) -> DomainInfo:
        for taco_domain in cls.SUPPORTED_DOMAINS:
            if taco_domain.name == domain:
                return taco_domain

        raise cls.Unrecognized(f"{domain} is not a recognized domain.")
