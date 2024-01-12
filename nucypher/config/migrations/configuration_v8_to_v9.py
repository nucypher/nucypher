from typing import Dict

from nucypher.config.migrations.common import perform_migration


def __migration(config: Dict) -> Dict:
    # deprecations
    del config["node_storage"]
    return config


def configuration_v8_to_v9(filepath) -> None:
    perform_migration(
        old_version=8, new_version=9, migration=__migration, filepath=filepath
    )
