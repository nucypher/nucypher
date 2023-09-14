from typing import Dict

from nucypher.blockchain.eth.networks import NetworksInventory
from nucypher.config.migrations.common import perform_migration


def __migration(config: Dict) -> Dict:
    eth_provider = config["eth_provider_uri"]
    eth_chain_id = NetworksInventory.get_ethereum_chain_id(config["domain"])

    polygon_provider = config["payment_provider"]
    del config["payment_provider"]
    config["pre_payment_provider"] = polygon_provider

    pre_payment_network = config["payment_network"]
    del config["payment_network"]
    config["pre_payment_network"] = pre_payment_network

    pre_payment_method = config["pre_payment_method"]
    del config["pre_payment_method"]
    config["pre_payment_method"] = pre_payment_method

    polygon_chain_id = NetworksInventory.get_polygon_chain_id(pre_payment_network)
    if "condition_provider_uris" in config:
        return config
    config["condition_provider_uris"] = {
        eth_chain_id: [eth_provider],
        polygon_chain_id: [polygon_provider],
    }
    return config


def configuration_v4_to_v6(filepath) -> None:
    perform_migration(
        old_version=4, new_version=6, migration=__migration, filepath=filepath
    )
