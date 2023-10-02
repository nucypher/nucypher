from enum import Enum
from typing import List, NamedTuple

from nucypher.config.constants import TEMPORARY_DOMAIN


class ChainInfo(NamedTuple):
    id: int
    name: str


class EthChain(ChainInfo, Enum):
    MAINNET = ChainInfo(1, "mainnet")
    GOERLI = ChainInfo(5, "goerli")
    SEPOLIA = ChainInfo(11155111, "sepolia")
    TESTERCHAIN = ChainInfo(131277322940537, TEMPORARY_DOMAIN)


class PolygonChain(ChainInfo, Enum):
    POLYGON = ChainInfo(137, "polygon")
    MUMBAI = ChainInfo(80001, "mumbai")
    TESTERCHAIN = ChainInfo(131277322940537, TEMPORARY_DOMAIN)


class TACoNetwork(NamedTuple):
    name: str
    eth_chain: EthChain
    polygon_chain: PolygonChain

    def is_testnet(self) -> bool:
        return self.eth_chain != EthChain.MAINNET


class UnrecognizedNetwork(RuntimeError):
    """Raised when a provided network name is not recognized."""


class NetworksInventory:
    MAINNET = TACoNetwork("mainnet", EthChain.MAINNET, PolygonChain.POLYGON)
    # Testnets
    ORYX = TACoNetwork("oryx", EthChain.GOERLI, PolygonChain.POLYGON)
    LYNX = TACoNetwork("lynx", EthChain.GOERLI, PolygonChain.MUMBAI)
    TAPIR = TACoNetwork("tapir", EthChain.SEPOLIA, PolygonChain.MUMBAI)
    # TODO did Ibex even use a PolyNetwork?
    IBEX = TACoNetwork(
        "ibex", EthChain.GOERLI, PolygonChain.MUMBAI
    )  # this is required for configuration file migrations (backwards compatibility)

    SUPPORTED_NETWORKS = [
        MAINNET,
        ORYX,
        LYNX,
        TAPIR,
        IBEX,
    ]

    SUPPORTED_NETWORK_NAMES = [network.name for network in SUPPORTED_NETWORKS]

    # TODO not needed once merged with registry changes
    POLYGON_CHAINS = [network.polygon_chain.name for network in SUPPORTED_NETWORKS]

    DEFAULT_NETWORK_NAME: str = MAINNET.name

    @classmethod
    def get_network(cls, network_name: str) -> TACoNetwork:
        for network in cls.SUPPORTED_NETWORKS:
            if network.name == network_name:
                return network

        raise UnrecognizedNetwork(f"{network_name} is not a recognized network.")

    @classmethod
    def get_network_names(cls) -> List[str]:
        networks = [network.name for network in cls.SUPPORTED_NETWORKS]
        return networks
