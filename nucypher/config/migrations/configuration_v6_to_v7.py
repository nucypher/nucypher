from typing import Dict

from nucypher.config.migrations.common import perform_migration


def __migration(config: Dict) -> Dict:
    # convert deprecated "payment_*" -> "pre_payment_*"
    config["pre_payment_provider"] = config["payment_provider"]
    del config["payment_provider"]

    config["pre_payment_network"] = config["payment_network"]
    del config["payment_network"]

    config["pre_payment_method"] = config["payment_method"]
    del config["payment_method"]

    # remove deprecated availability check
    del config["availability_check"]

    return config


def configuration_v6_to_v7(filepath) -> None:
    perform_migration(
        old_version=6, new_version=7, migration=__migration, filepath=filepath
    )
