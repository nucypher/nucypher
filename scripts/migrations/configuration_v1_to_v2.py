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


def configuration_v1_to_v2(filepath: str):
    """Updates configuration file V2 to V2 by remapping 'domains' to 'domain'"""

    # Read + deserialize
    with open(filepath, 'r') as file:
        contents = file.read()
    config = json.loads(contents)

    # Check we have version 1 indeed
    if config['version'] != 1:
        raise RuntimeError('Existing configuration is not version 1.')

    # Make a copy of the original file
    backup_filepath = filepath+BACKUP_SUFFIX
    os.rename(filepath, backup_filepath)
    print(f'Backed up existing configuration to {backup_filepath}')

    # Get current domain value
    domains = config['domains']
    domian = domains[0]
    if len(domains) > 1:
        print(f'Multiple domains configured, selecting the first one ({domian}).')

    # Apply updates
    del config['domains']  # deprecated
    config['domain'] = domian
    config['version'] = 2

    # Commit updates
    with open(filepath, 'w') as file:
        file.write(json.dumps(config, indent=4))
    print('OK! Migrated configuration file from v1 -> v2.')


if __name__ == "__main__":
    try:
        _python, filepath = sys.argv
    except IndexError:
        raise ValueError('Configuration filepath is required')
    except ValueError:
        raise ValueError('Too many arguments, pass the filepath only.')
    configuration_v1_to_v2(filepath=filepath)
