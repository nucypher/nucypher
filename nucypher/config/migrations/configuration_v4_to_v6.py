from typing import Dict

from nucypher.blockchain.eth.networks import NetworksInventory
from nucypher.config.migrations.common import perform_migration


def __migration(config: Dict) -> None:
    del config["federated_only"]  # deprecated
    del config["checksum_address"]

    # Multichain support
    eth_provider = config["eth_provider_uri"]
    eth_chain_id = NetworksInventory.get_ethereum_chain_id(config["domain"])
    polygon_provider = config["payment_provider"]
    polygon_chain_id = NetworksInventory.get_polygon_chain_id(config["payment_network"])
    config["condition_provider_uris"] = {
        eth_chain_id: [eth_provider],
        polygon_chain_id: [polygon_provider],
    }


def configuration_v4_to_v6(filepath) -> None:
    perform_migration(
        old_version=4, new_version=6, migration=__migration, filepath=filepath
    )
