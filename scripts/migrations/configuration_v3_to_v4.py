#!/usr/bin/env python

"""
 This file is part of nucypher.

 nucypher is free software: you can redistribute it and/or modify
 it under the terms of the GNU Affero General Public License as published by
 the Free Software Foundation, either version 3 of the License, or
 (at your option) any later version.

 nucypher is distributed in the hope that it will be useful,
 but WITHOUT ANY WARRANTY; without even the implied warranty of
 MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
 GNU Affero General Public License for more details.

 You should have received a copy of the GNU Affero General Public License
 along with nucypher.  If not, see <https://www.gnu.org/licenses/>.
"""

import json

import os
import sys

BACKUP_SUFFIX = '.old'
OLD_VERSION = 3
NEW_VERSION = 4


def configuration_v3_to_v4(filepath: str):
    """Updates configuration file v3 to v4 by remapping 'domains' to 'domain'"""

    # Read + deserialize
    with open(filepath, 'r') as file:
        contents = file.read()
    config = json.loads(contents)

    try:
        # Check we have version 1 indeed
        existing_version = config['version']
        if existing_version != OLD_VERSION:
            raise RuntimeError(f'Existing configuration is not version 1; Got version {existing_version}')

        # Make a copy of the original file
        backup_filepath = filepath+BACKUP_SUFFIX
        os.rename(filepath, backup_filepath)
        print(f'Backed up existing configuration to {backup_filepath}')

        # Apply updates
        worker_address = config['worker_address']
        del config['worker_address']  # deprecated
        config['operator_address'] = worker_address
        config['version'] = NEW_VERSION

    except KeyError:
        raise RuntimeError(f'Invalid {OLD_VERSION} configuration file.')

    # Commit updates
    with open(filepath, 'w') as file:
        file.write(json.dumps(config, indent=4))
    print('OK! Migrated configuration file from v3 -> v4.')


if __name__ == "__main__":
    try:
        _python, filepath = sys.argv
    except ValueError:
        raise ValueError('Invalid command: Provide a single configuration filepath.')
    configuration_v3_to_v4(filepath=filepath)
