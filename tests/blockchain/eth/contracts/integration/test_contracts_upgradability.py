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
import os
import tempfile

import pytest
import requests

from nucypher.blockchain.eth.sol.compile import SolidityCompiler, SourceDirs
from nucypher.crypto.powers import TransactingPower
from nucypher.utilities.sandbox.constants import INSECURE_DEVELOPMENT_PASSWORD

USER = "nucypher"
REPO = "nucypher"
BRANCH = "master"
GITHUB_SOURCE_LINK = f"https://api.github.com/repos/{USER}/{REPO}/contents/nucypher/blockchain/eth/sol/source?ref={BRANCH}"


def download_github_dir(source_link: str, target_folder: str):
    response = requests.get(source_link)
    if response.status_code != 200:
        error = f"Failed to call api {source_link} with status code {response.status_code}"
        raise RuntimeError(error)

    for content in response.json():
        path = os.path.join(target_folder, content["name"])
        if content["type"] == "dir":
            os.mkdir(path)
            download_github_dir(content["url"], path)
        else:
            download_github_file(content["download_url"], path)


def download_github_file(source_link: str, target_folder: str):
    response = requests.get(source_link)
    if response.status_code != 200:
        error = f"Failed to call api {source_link} with status code {response.status_code}"
        raise RuntimeError(error)

    raw_data = response.content
    with open(target_folder, 'wb') as registry_file:
        registry_file.seek(0)
        registry_file.write(raw_data)
        registry_file.truncate()


@pytest.mark.slow
def test_upgradability():
    with tempfile.TemporaryDirectory() as temp_dir:
        download_github_dir(GITHUB_SOURCE_LINK, temp_dir)
        solidity_compiler = SolidityCompiler(source_dirs=[SourceDirs(SolidityCompiler.default_contract_dir()),
                                                          SourceDirs(temp_dir)])
        interfaces = solidity_compiler.compile()
        pass
    pass
