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


import contextlib
import json
import os
import shutil
import sys

import pytest
from click.testing import CliRunner

from nucypher.blockchain.eth.registry import AllocationRegistry
from nucypher.config.characters import UrsulaConfiguration
from nucypher.utilities.sandbox.constants import (
    MOCK_CUSTOM_INSTALLATION_PATH,
    MOCK_ALLOCATION_INFILE,
    MOCK_REGISTRY_FILEPATH,
    ONE_YEAR_IN_SECONDS)
from nucypher.utilities.sandbox.constants import MOCK_CUSTOM_INSTALLATION_PATH_2, INSECURE_DEVELOPMENT_PASSWORD


@pytest.fixture(scope='module')
def click_runner():
    runner = CliRunner()
    yield runner


@pytest.fixture(scope='session')
def deploy_user_input():
    account_index = '0\n'
    yes = 'Y\n'
    deployment_secret = f'{INSECURE_DEVELOPMENT_PASSWORD}\n'
    user_input = account_index + yes + (deployment_secret * 8) + 'DEPLOY'
    return user_input


@pytest.fixture(scope='session')
def nominal_federated_configuration_fields():
    config = UrsulaConfiguration(dev_mode=True, federated_only=True)
    config_fields = config.static_payload()
    yield tuple(config_fields.keys())
    del config


@pytest.fixture(scope='module')
def mock_allocation_infile(testerchain, token_economics):
    accounts = testerchain.unassigned_accounts
    allocation_data = [{'staker_address': addr,
                        'amount': token_economics.minimum_allowed_locked,
                        'lock_periods': ONE_YEAR_IN_SECONDS}
                       for addr in accounts]

    with open(MOCK_ALLOCATION_INFILE, 'w') as file:
        file.write(json.dumps(allocation_data))

    registry = AllocationRegistry(filepath=MOCK_ALLOCATION_INFILE)
    yield registry
    os.remove(MOCK_ALLOCATION_INFILE)


@pytest.mark.usefixtures("agency")  # TODO: usesfixtures not working here
@pytest.fixture(scope='module', autouse=True)
def mock_primary_registry_filepath(test_registry, agency):
    # Create filesystem registry from memory.
    filepath = test_registry.commit(filepath=MOCK_REGISTRY_FILEPATH)
    assert filepath == MOCK_REGISTRY_FILEPATH
    assert os.path.isfile(MOCK_REGISTRY_FILEPATH)
    yield MOCK_REGISTRY_FILEPATH
    if os.path.isfile(MOCK_REGISTRY_FILEPATH):
        os.remove(MOCK_REGISTRY_FILEPATH)


@pytest.fixture(scope='module')
def custom_filepath():
    _custom_filepath = MOCK_CUSTOM_INSTALLATION_PATH
    with contextlib.suppress(FileNotFoundError):
        shutil.rmtree(_custom_filepath, ignore_errors=True)
    try:
        yield _custom_filepath
    finally:
        with contextlib.suppress(FileNotFoundError):
            shutil.rmtree(_custom_filepath, ignore_errors=True)


@pytest.fixture(scope='module')
def custom_filepath_2():
    _custom_filepath = MOCK_CUSTOM_INSTALLATION_PATH_2
    with contextlib.suppress(FileNotFoundError):
        shutil.rmtree(_custom_filepath, ignore_errors=True)
    try:
        yield _custom_filepath
    finally:
        with contextlib.suppress(FileNotFoundError):
            shutil.rmtree(_custom_filepath, ignore_errors=True)
