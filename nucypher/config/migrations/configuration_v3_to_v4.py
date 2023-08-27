from typing import Dict

from nucypher.config.migrations.common import perform_migration


def __migration(config: Dict) -> Dict:
    worker_address = config["worker_address"]
    del config["worker_address"]  # deprecated
    config["operator_address"] = worker_address
    return config


def configuration_v3_to_v4(filepath) -> None:
    perform_migration(
        old_version=3, new_version=4, migration=__migration, filepath=filepath
    )
