import json
import os
from pathlib import Path
from typing import Callable, Dict, Tuple

BACKUP_SUFFIX = ".old"


class WrongConfigurationVersion(Exception):
    pass


class InvalidMigration(Exception):
    pass


def __prepare_migration(old_version: int, filepath: Path) -> Tuple[Dict, Path]:
    # Read + deserialize
    with open(filepath, "r") as file:
        contents = file.read()
    config = json.loads(contents)

    # verify the correct version is being migrated
    existing_version = config["version"]
    if existing_version != old_version:
        raise WrongConfigurationVersion(
            f"Existing configuration is not version {old_version}; Got version {existing_version}"
        )

    # Make a copy of the original file
    backup_filepath = str(filepath) + BACKUP_SUFFIX
    os.rename(filepath, backup_filepath)
    print(f"Backed up existing configuration to {backup_filepath}")
    return config, Path(backup_filepath)


def __finalize_migration(config: Dict, new_version: int, filepath: Path):
    config["version"] = new_version
    with open(filepath, "w") as file:
        file.write(json.dumps(config, indent=4))


def perform_migration(
    old_version: int, new_version: int, migration: Callable, filepath: str
):
    try:
        config, backup_filepath = __prepare_migration(
            old_version=old_version, filepath=Path(filepath)
        )
    except WrongConfigurationVersion:
        raise
    try:
        config = migration(config)
    except KeyError:
        os.rename(str(backup_filepath), filepath)  # rollback the changes
        raise InvalidMigration(f"Invalid v{old_version} configuration file.")
    __finalize_migration(
        config=config, new_version=new_version, filepath=Path(filepath)
    )
    print(
        f"OK! Migrated configuration file {filepath} from v{old_version} -> v{new_version}."
    )
