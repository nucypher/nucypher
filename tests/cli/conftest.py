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
from io import StringIO

import os
import pytest
import shutil
from click.testing import CliRunner
from datetime import datetime

from nucypher.blockchain.eth.registry import InMemoryContractRegistry, LocalContractRegistry
from nucypher.characters.control.emitters import StdoutEmitter
from nucypher.config.characters import StakeHolderConfiguration, UrsulaConfiguration
from tests.constants import (
    BASE_TEMP_DIR,
    BASE_TEMP_PREFIX,
    DATETIME_FORMAT,
    MOCK_ALLOCATION_INFILE,
    MOCK_CUSTOM_INSTALLATION_PATH,
    MOCK_CUSTOM_INSTALLATION_PATH_2
)


@pytest.fixture(scope='function', autouse=True)
def stdout_trap(mocker):
    trap = StringIO()
    mocker.patch('sys.stdout', new=trap)
    return trap


@pytest.fixture(scope='function')
def test_emitter(mocker, stdout_trap):
    mocker.patch('sys.stdout', new=stdout_trap)
    return StdoutEmitter()


@pytest.fixture(scope='module')
def click_runner():
    runner = CliRunner()
    yield runner


@pytest.fixture(scope='session')
def nominal_federated_configuration_fields():
    config = UrsulaConfiguration(dev_mode=True, federated_only=True)
    config_fields = config.static_payload()
    yield tuple(config_fields.keys())
    del config


@pytest.fixture(scope='module')
def mock_allocation_infile(testerchain, token_economics, get_random_checksum_address):
    accounts = [get_random_checksum_address() for _ in range(10)]
    # accounts = testerchain.unassigned_accounts
    allocation_data = list()
    amount = 2 * token_economics.minimum_allowed_locked
    min_periods = token_economics.minimum_locked_periods
    for account in accounts:
        substake = [{'checksum_address': account, 'amount': amount, 'lock_periods': min_periods + i} for i in range(24)]
        allocation_data.extend(substake)

    with open(MOCK_ALLOCATION_INFILE, 'w') as file:
        file.write(json.dumps(allocation_data))

    yield MOCK_ALLOCATION_INFILE
    if os.path.isfile(MOCK_ALLOCATION_INFILE):
        os.remove(MOCK_ALLOCATION_INFILE)


@pytest.fixture(scope='function')
def new_local_registry():
    filename = f'{BASE_TEMP_PREFIX}mock-empty-registry-{datetime.now().strftime(DATETIME_FORMAT)}.json'
    registry_filepath = os.path.join(BASE_TEMP_DIR, filename)
    registry = LocalContractRegistry(filepath=registry_filepath)
    registry.write(InMemoryContractRegistry().read())
    yield registry
    if os.path.exists(registry_filepath):
        os.remove(registry_filepath)


@pytest.fixture(scope='module')
def custom_filepath():
    _custom_filepath = MOCK_CUSTOM_INSTALLATION_PATH
    with contextlib.suppress(FileNotFoundError):
        shutil.rmtree(_custom_filepath, ignore_errors=True)
    yield _custom_filepath
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


@pytest.fixture(scope='module')
def worker_configuration_file_location(custom_filepath):
    _configuration_file_location = os.path.join(MOCK_CUSTOM_INSTALLATION_PATH,
                                                UrsulaConfiguration.generate_filename())
    return _configuration_file_location


@pytest.fixture(scope='module')
def stakeholder_configuration_file_location(custom_filepath):
    _configuration_file_location = os.path.join(MOCK_CUSTOM_INSTALLATION_PATH,
                                                StakeHolderConfiguration.generate_filename())
    return _configuration_file_location
