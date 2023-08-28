from typing import Dict

from nucypher.config.migrations.common import perform_migration


def __migration(config: Dict) -> Dict:
    domains = config["domains"]
    domain = domains[0]
    if len(domains) > 1:
        print(f"Multiple domains configured, using the first one ({domain}).")
    del config["domains"]
    config["domain"] = domain
    return config


def configuration_v1_to_v2(filepath) -> None:
    perform_migration(
        old_version=1, new_version=2, migration=__migration, filepath=filepath
    )
