from typing import Dict

from nucypher.config.migrations.common import perform_migration


def __migration(config: Dict) -> None:
    del config["federated_only"]  # deprecated
    del config["checksum_address"]


def configuration_v4_to_v5(filepath) -> None:
    perform_migration(
        old_version=4, new_version=5, migration=__migration, filepath=filepath
    )
