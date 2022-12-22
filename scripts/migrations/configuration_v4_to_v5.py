#!/usr/bin/env python


import json
import os

import sys

BACKUP_SUFFIX = '.old'
OLD_VERSION = 4
NEW_VERSION = 5


def configuration_v4_to_v5(filepath: str):
    """Updates configuration file v3 to v4 by remapping 'domains' to 'domain'"""

    # Read + deserialize
    with open(filepath, 'r') as file:
        contents = file.read()
    config = json.loads(contents)

    try:
        existing_version = config['version']
        if existing_version != OLD_VERSION:
            raise RuntimeError(f'Existing configuration is not version {OLD_VERSION}; Got version {existing_version}')

        # Make a copy of the original file
        backup_filepath = filepath+BACKUP_SUFFIX
        os.rename(filepath, backup_filepath)
        print(f'Backed up existing configuration to {backup_filepath}')

        # Apply updates
        del config['federated_only']  # deprecated
        del config['checksum_address']
        config['version'] = NEW_VERSION

    except KeyError:
        raise RuntimeError(f'Invalid {OLD_VERSION} configuration file.')

    # Commit updates
    with open(filepath, 'w') as file:
        file.write(json.dumps(config, indent=4))
    print(f'OK! Migrated configuration file from v{OLD_VERSION} -> v{NEW_VERSION}.')


if __name__ == "__main__":
    try:
        _python, filepath = sys.argv
    except ValueError:
        raise ValueError('Invalid command: Provide a single configuration filepath.')
    configuration_v4_to_v5(filepath=filepath)
