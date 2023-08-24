import json
import os

BACKUP_SUFFIX = ".old"
OLD_VERSION = 1
NEW_VERSION = 2


def configuration_v1_to_v2(filepath: str):
    # Read + deserialize
    with open(filepath, "r") as file:
        contents = file.read()
    config = json.loads(contents)

    try:
        # Check we have version 1 indeed
        existing_version = config["version"]
        if existing_version != OLD_VERSION:
            raise RuntimeError(
                f"Existing configuration is not version 1; Got version {existing_version}"
            )

        # Make a copy of the original file
        backup_filepath = str(filepath) + BACKUP_SUFFIX
        os.rename(filepath, backup_filepath)
        print(f"Backed up existing configuration to {backup_filepath}")

        # Get current domain value
        domains = config["domains"]
        domain = domains[0]
        if len(domains) > 1:
            print(f"Multiple domains configured, using the first one ({domain}).")

        # Apply updates
        del config["domains"]  # deprecated
        config["domain"] = domain
        config["version"] = NEW_VERSION
    except KeyError:
        raise KeyError(f"Invalid {OLD_VERSION} configuration file.")

    # Commit updates
    with open(filepath, "w") as file:
        file.write(json.dumps(config, indent=4))
    print("OK! Migrated configuration file from v1 -> v2.")
