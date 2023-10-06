from typing import Dict

from nucypher.config.migrations.common import perform_migration


def __migration(config: Dict) -> Dict:
    # deprecations
    del config["pre_payment_network"]

    # eth_provider_uri -> eth_endpoint
    config["eth_endpoint"] = config["eth_provider_uri"]
    del config["eth_provider_uri"]

    # pre_payment_provider -> polygon_endpoint
    config["polygon_endpoint"] = config["pre_payment_provider"]
    del config["pre_payment_provider"]

    # condition_provider_uris -> condition_blockchain_endpoints
    config["condition_blockchain_endpoints"] = config["condition_provider_uris"]
    del config["condition_provider_uris"]

    return config


def configuration_v7_to_v8(filepath) -> None:
    perform_migration(
        old_version=7, new_version=8, migration=__migration, filepath=filepath
    )
