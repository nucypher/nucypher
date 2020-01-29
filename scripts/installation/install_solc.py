#!/usr/bin/env python

import platform
import shutil
from os.path import dirname, join, abspath
from os import stat, chmod
import requests


if platform.system() != 'Linux':
    raise EnvironmentError("This installation script is only compatible with linux-gnu-based operating systems.")

PACKAGE_NAME = join('nucypher', 'blockchain', 'eth', 'sol')
BASE_DIR = dirname(dirname(dirname(abspath(__file__))))
FILE_PATH = join(BASE_DIR, PACKAGE_NAME, "__init__.py")

METADATA = dict()
with open(FILE_PATH) as f:
    exec(f.read(), METADATA)

solc_version = METADATA['SOLIDITY_COMPILER_VERSION']

# Get solc binary for linux
solc_bin_path=join(dirname(shutil.which('python')), 'solc')
url = f"https://github.com/ethereum/solidity/releases/download/v{solc_version}/solc-static-linux"
print(f"Downloading solidity compiler binary from {url} to {solc_bin_path}")

response = requests.get(url)
response.raise_for_status()
with open(solc_bin_path, 'wb') as f:
    f.write(response.content)

# Set executable permission
print(f"Setting executable permission on {solc_bin_path}")
file_stat = stat(solc_bin_path)
chmod(solc_bin_path, 0o0755)

print(f"Successfully Installed solc {solc_version}")
