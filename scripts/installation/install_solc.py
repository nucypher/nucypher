#!/usr/bin/env python3

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

"""
Download supported version of solidity compiler for the host operating system.

This script depends on `nucypher.blockchain.eth.sol` submodule and `py-solc-x` library 
but otherwise does not require installation of `nucypher` or its dependencies. 
"""


import os
import sys
from pathlib import Path


def get_solc_config_path() -> Path:
    # Note: This script is sensitive to the working directory.
    nucypher = Path(__file__).parent.parent.parent.resolve() / 'nucypher'
    config_path = nucypher / 'blockchain' / 'eth' / 'sol' / '__conf__.py'
    return config_path


def get_packaged_solc_version() -> str:
    """Returns the solidity version specified in the embedded configuration file"""
    solc_config = get_solc_config_path()
    metadata = dict()
    with open(str(solc_config)) as f:
        exec(f.read(), metadata)  # noqa
    version = metadata['SOLIDITY_COMPILER_VERSION']
    return version


def get_solc_version() -> str:
    """
    Returns a solidity version string.  Resolves the solidity version in the following priority:

    HIGH PRIORITY
    1. Command line argument
    2. Environment variable
    3. Packaged contract version
    LOW PRIORITY
    """
    try:
        version = sys.argv[1]  # 1
    except IndexError:
        try:
            version = os.environ['NUCYPHER_SOLIDITY_VERSION']  # 2
        except KeyError:
            version = get_packaged_solc_version()  # 3
    return version


def install_solc(version: str) -> None:
    """Install the solidity compiler binary to the system for the specified version then set it as the default."""
    try:
        from solcx import install_solc, set_solc_version
    except ImportError:
        error = f"Failed to install solc, py-solc-x  is not found. " \
                f"Install with 'pip install py-solc-x' and try again."
        raise ImportError(error)

    install_solc(version)


def main():
    version = get_solc_version()
    print(f"Fetched solc version {version} from source configuration")

    install_solc(version=version)
    print(f"Successfully installed solc {version}")


if __name__ == "__main__":
    main()
