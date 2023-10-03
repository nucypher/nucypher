class NetworksInventory:  # TODO: See #1564

    MAINNET = "mainnet"
    LYNX = "lynx"
    IBEX = "ibex"  # this is required for configuration file migrations (backwards compatibility)
    ETH = "ethereum"
    TAPIR = "tapir"
    ORYX = "oryx"

    # TODO: Use naming scheme to preserve multiple compatibility with multiple deployments to a single network?
    POLYGON = 'polygon'
    MUMBAI = 'mumbai'

    UNKNOWN = 'unknown'  # TODO: Is there a better way to signal an unknown network?
    DEFAULT = MAINNET

    __to_chain_id_eth = {
        MAINNET: 1,  # Ethereum Mainnet
        IBEX: 5,  # this is required for configuration file migrations (backwards compatibility)
        LYNX: 5,  # Goerli
        TAPIR: 11155111,  # Sepolia
        ORYX: 5,  # Goerli
    }
    __to_chain_id_polygon = {
        # TODO: Use naming scheme?
        POLYGON: 137,    # Polygon Mainnet
        MUMBAI: 80001,   # Polygon Testnet (Mumbai)
    }

    ETH_NETWORKS = tuple(__to_chain_id_eth.keys())
    POLY_NETWORKS = tuple(__to_chain_id_polygon.keys())

    NETWORKS = ETH_NETWORKS + POLY_NETWORKS

    class UnrecognizedNetwork(RuntimeError):
        pass

    @classmethod
    def get_ethereum_chain_id(cls, network):
        try:
            return cls.__to_chain_id_eth[network]
        except KeyError:
            raise cls.UnrecognizedNetwork(network)

    @classmethod
    def get_polygon_chain_id(cls, network):
        try:
            return cls.__to_chain_id_polygon[network]
        except KeyError:
            raise cls.UnrecognizedNetwork(network)

    @classmethod
    def validate_network_name(cls, network_name: str):
        if network_name not in cls.NETWORKS:
            raise cls.UnrecognizedNetwork(
                f"{network_name} is not a recognized network."
            )
