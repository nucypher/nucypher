from typing import Dict

from nucypher.config.migrations.common import perform_migration


def __migration(config: Dict) -> Dict:
    deprecations = [
        "pre_payment_network",
        "poa",
        "light",
        "learn_on_same_thread",
        "start_learning_now",
        "learn_on_same_thread",
        "abort_on_learning_error",
        "save_metadata",
        "node_storage",
        "lonely",
        "gas_strategy",
        "max_gas_price",
        "operator_address",
        "db_filepath",
        "availability_check",
        "payment_method",
        "payment_provider",
        "payment_network",
    ]

    for deprecated_key in deprecations:
        if deprecated_key in config:
            try:
                del config[deprecated_key]
            except KeyError:
                pass

    # signer_uri -> wallet_filepath
    try:
        signer_uri = config["signer_uri"]
    except KeyError:
        raise ValueError("Invalid configuration: no signer_uri")
    prefix = "keystore://"
    config["wallet_filepath"] = signer_uri.lstrip(prefix)
    del config["signer_uri"]

    # keystore_path -> keystore_filepath
    try:
        config["keystore_filepath"] = config["keystore_filepath"]
    except KeyError:
        raise ValueError("Invalid configuration: no keystore_filepath")
    del config["keystore_filepath"]

    return config


def configuration_v8_to_v9(filepath) -> None:
    perform_migration(
        old_version=8, new_version=9, migration=__migration, filepath=filepath
    )
