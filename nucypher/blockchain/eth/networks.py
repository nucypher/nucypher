from enum import Enum
from typing import List, NamedTuple

from nucypher.config.constants import TEMPORARY_DOMAIN


class ChainInfo(NamedTuple):
    chain_id: int
    chain_name: str

    # Override eventual Enum name. TODO: better way?
    @property
    def name(self) -> str:
        return self.chain_name


class EthNetwork(ChainInfo, Enum):
    MAINNET = ChainInfo(1, "mainnet")
    GOERLI = ChainInfo(5, "goerli")
    SEPOLIA = ChainInfo(11155111, "sepolia")
    # testing
    TESTERCHAIN = ChainInfo(131277322940537, TEMPORARY_DOMAIN)


class PolyNetwork(ChainInfo, Enum):
    POLYGON = ChainInfo(137, "polygon")
    MUMBAI = ChainInfo(80001, "mumbai")
    # testing
    TESTERCHAIN = ChainInfo(131277322940537, TEMPORARY_DOMAIN)


class TACoNetwork(NamedTuple):
    name: str
    eth_network: EthNetwork
    poly_network: PolyNetwork

    def is_testnet(self) -> bool:
        return self.eth_network != EthNetwork.MAINNET


class UnrecognizedNetwork(RuntimeError):
    """Raised when a provided network name is not recognized."""
    pass


class NetworksInventory:
    MAINNET = TACoNetwork("mainnet", EthNetwork.MAINNET, PolyNetwork.POLYGON)
    # Testnets
    ORYX = TACoNetwork("oryx", EthNetwork.GOERLI, PolyNetwork.POLYGON)
    LYNX = TACoNetwork("lynx", EthNetwork.GOERLI, PolyNetwork.MUMBAI)
    TAPIR = TACoNetwork("tapir", EthNetwork.SEPOLIA, PolyNetwork.MUMBAI)
    # TODO did Ibex even use a PolyNetwork?
    IBEX = TACoNetwork(
        "ibex", EthNetwork.GOERLI, PolyNetwork.MUMBAI
    )  # this is required for configuration file migrations (backwards compatibility)

    SUPPORTED_NETWORKS = [
        MAINNET,
        ORYX,
        LYNX,
        TAPIR,
        IBEX,
    ]

    SUPPORTED_NETWORK_NAMES = [network.name for network in SUPPORTED_NETWORKS]

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
