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

import pytest
from click.testing import CliRunner

from nucypher.blockchain.eth.actors import ContractAdministrator
from nucypher.blockchain.eth.registry import AllocationRegistry, InMemoryContractRegistry
from nucypher.config.characters import UrsulaConfiguration, StakeHolderConfiguration
from nucypher.utilities.sandbox.constants import (
    MOCK_ALLOCATION_REGISTRY_FILEPATH,
    MOCK_CUSTOM_INSTALLATION_PATH,
    MOCK_CUSTOM_INSTALLATION_PATH_2,
    INSECURE_DEVELOPMENT_PASSWORD,
    MOCK_ALLOCATION_INFILE,
    MOCK_REGISTRY_FILEPATH,
    ONE_YEAR_IN_SECONDS)


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
    allocation_data = [{'beneficiary_address': addr,
                        'amount': 2 * token_economics.minimum_allowed_locked,
                        'duration_seconds': ONE_YEAR_IN_SECONDS}
                       for addr in accounts]

    with open(MOCK_ALLOCATION_INFILE, 'w') as file:
        file.write(json.dumps(allocation_data))

    yield MOCK_ALLOCATION_INFILE
    if os.path.isfile(MOCK_ALLOCATION_INFILE):
        os.remove(MOCK_ALLOCATION_INFILE)


@pytest.fixture(scope='module')
def mock_allocation_registry(testerchain, test_registry, mock_allocation_infile):
    admin = ContractAdministrator(registry=test_registry,
                                  client_password=INSECURE_DEVELOPMENT_PASSWORD,
                                  deployer_address=testerchain.etherbase_account)

    admin.deploy_beneficiaries_from_file(allocation_data_filepath=mock_allocation_infile,
                                         allocation_outfile=MOCK_ALLOCATION_REGISTRY_FILEPATH)

    allocation_registry = AllocationRegistry(filepath=MOCK_ALLOCATION_REGISTRY_FILEPATH)
    yield allocation_registry
    if os.path.isfile(MOCK_ALLOCATION_REGISTRY_FILEPATH):
        os.remove(MOCK_ALLOCATION_REGISTRY_FILEPATH)


@pytest.fixture(scope='module', autouse=True)
def temp_registry(testerchain, test_registry, agency):
    registry_filepath = MOCK_REGISTRY_FILEPATH
    # Disable registry fetching, use the mock one instead
    InMemoryContractRegistry.download_latest_publication = lambda: registry_filepath
    filepath = test_registry.commit(filepath=registry_filepath, overwrite=True)
    assert filepath == MOCK_REGISTRY_FILEPATH
    assert os.path.isfile(MOCK_REGISTRY_FILEPATH)
    yield registry_filepath
    if os.path.exists(registry_filepath):
        os.remove(registry_filepath)


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
