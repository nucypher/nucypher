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
Download supported version of solidity compiler for Linux based operating system. 
This script depends on `nucypher.blockchain.eth.sol` submodule and `requests` library 
but does not require installation of `nucypher`. 
"""

import platform
import shutil
from os.path import dirname, join, abspath
from os import chmod
import requests

PACKAGE_NAME = join('nucypher', 'blockchain', 'eth', 'sol')
BASE_DIR = dirname(dirname(dirname(abspath(__file__))))
FILE_PATH = join(BASE_DIR, PACKAGE_NAME, "__conf__.py")

METADATA = dict()
with open(FILE_PATH) as f:
    exec(f.read(), METADATA)

SOLC_VERSION = METADATA['SOLIDITY_COMPILER_VERSION']
SOLC_BIN_PATH = join(dirname(shutil.which('python')), 'solc')


def download_solc_binary():
    url = f"https://github.com/ethereum/solidity/releases/download/v{SOLC_VERSION}/solc-static-linux"
    print(f"Downloading solidity compiler binary from {url} to {SOLC_BIN_PATH}")

    response = requests.get(url)
    response.raise_for_status()
    with open(SOLC_BIN_PATH, 'wb') as f:
        f.write(response.content)

    # Set executable permission
    print(f"Setting executable permission on {SOLC_BIN_PATH}")
    executable_mode = 0o0755
    chmod(SOLC_BIN_PATH, executable_mode)

    print(f"Successfully Installed solc {SOLC_VERSION}")


if __name__ == "__main__":

    if platform.system() != 'Linux':
        raise EnvironmentError("This installation script is only compatible with linux-gnu-based operating systems.")

    # Get solc binary for linux
    download_solc_binary()
