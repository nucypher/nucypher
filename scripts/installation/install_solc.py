#!/usr/bin/env python3

"""
Download supported version of solidity compiler for the host operating system.

This script depends on `nucypher.blockchain.eth.sol` submodule and `py-solc-x` library 
but otherwise does not require installation of `nucypher` or it's dependencies. 
"""

import os
from os.path import dirname, abspath
from pathlib import Path

from solcx import install_solc, set_solc_version


def get_solc_version() -> str:

    env_version = os.environ.get('NUCYPHER_SOLIDITY_VERSION')
    if env_version:
        return env_version

    nucypher = Path('nucypher')
    sol_package_path = nucypher / 'blockchain' / 'eth' / 'sol'
    base_dir = Path(dirname(dirname(dirname(abspath(__file__)))))
    file_path = base_dir / sol_package_path / "__conf__.py"

    metadata = dict()
    with open(file_path) as f:
        exec(f.read(), metadata)

    version = metadata['SOLIDITY_COMPILER_VERSION']
    return version


def main():

    version = get_solc_version()
    print(f"Fetched solc version {version} from source configuration")

    install_solc(version)
    print(f"Successfully installed solc {version}")
    set_solc_version(version)


if __name__ == "__main__":
    main()
