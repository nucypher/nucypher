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

from nucypher.blockchain.eth.actors import Deployer
from nucypher.blockchain.eth.constants import MAX_ALLOWED_LOCKED, ONE_YEAR_IN_SECONDS
from nucypher.blockchain.eth.interfaces import BlockchainDeployerInterface
from nucypher.blockchain.eth.registry import InMemoryEthereumContractRegistry, InMemoryAllocationRegistry, \
    AllocationRegistry
from nucypher.blockchain.eth.sol.compile import SolidityCompiler
from nucypher.config.characters import UrsulaConfiguration
from nucypher.utilities.sandbox.blockchain import TesterBlockchain
from nucypher.utilities.sandbox.constants import MOCK_CUSTOM_INSTALLATION_PATH, TEST_PROVIDER_URI, \
    MOCK_ALLOCATION_INFILE, MOCK_REGISTRY_FILEPATH, TESTING_ETH_AIRDROP_AMOUNT
from nucypher.utilities.sandbox.constants import MOCK_CUSTOM_INSTALLATION_PATH_2


@pytest.fixture(scope='module')
def click_runner():
    runner = CliRunner()
    yield runner


@pytest.fixture(scope='module')
def nominal_federated_configuration_fields():
    config = UrsulaConfiguration(dev_mode=True, federated_only=True)
    config_fields = config.static_payload
    del config_fields['is_me']
    yield tuple(config_fields.keys())
    del config


@pytest.fixture(scope='module')
def mock_allocation_infile(testerchain):
    accounts = testerchain.interface.w3.eth.accounts[5::]
    allocation_data = [{'address': addr, 'amount': MAX_ALLOWED_LOCKED, 'duration': ONE_YEAR_IN_SECONDS} for addr in accounts]
    with open(MOCK_ALLOCATION_INFILE, 'w') as file:
        file.write(json.dumps(allocation_data))
    registry = AllocationRegistry(registry_filepath=MOCK_ALLOCATION_INFILE)
    yield registry
    os.remove(MOCK_ALLOCATION_INFILE)


@pytest.fixture(scope='module', autouse=True)
def mock_primary_registry_filepath():
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


@pytest.fixture(scope='session')
def deployed_blockchain():

    # Interface
    compiler = SolidityCompiler()
    registry = InMemoryEthereumContractRegistry()
    allocation_registry = InMemoryAllocationRegistry()
    interface = BlockchainDeployerInterface(compiler=compiler,
                                            registry=registry,
                                            provider_uri=TEST_PROVIDER_URI)

    # Blockchain
    blockchain = TesterBlockchain(interface=interface, airdrop=True, test_accounts=5, poa=True)
    deployer_address = blockchain.etherbase_account

    # Deployer
    deployer = Deployer(blockchain=blockchain,
                        deployer_address=deployer_address)

    # The Big Three (+ Dispatchers)
    deployer.deploy_network_contracts(miner_secret=os.urandom(32),
                                      policy_secret=os.urandom(32))

    # User Escrow Proxy
    deployer.deploy_escrow_proxy(secret=os.urandom(32))

    # Start with some hard-coded cases...
    all_yall = blockchain.unassigned_accounts
    allocation_data = [{'address': all_yall[1], 'amount': MAX_ALLOWED_LOCKED, 'duration': ONE_YEAR_IN_SECONDS}]

    deployer.deploy_beneficiary_contracts(allocations=allocation_data, allocation_registry=allocation_registry)

    yield blockchain, deployer_address, registry


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
