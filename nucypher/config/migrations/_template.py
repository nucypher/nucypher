from typing import Dict

from nucypher.config.migrations.common import perform_migration


def __migration(config: Dict) -> None:
    pass  # apply migrations here


def configuration_v1_to_v2(filepath) -> None:  # rename accordingly
    perform_migration(
        old_version=1,  # migrating from version
        new_version=2,  # migrating to version
        migration=__migration,
        filepath=filepath,
    )
