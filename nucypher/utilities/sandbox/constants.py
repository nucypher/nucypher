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
import os
import socket
import time
from datetime import datetime
from random import SystemRandom
from string import digits, ascii_uppercase

from web3 import Web3

from nucypher.blockchain.eth.token import NU
from nucypher.config.characters import UrsulaConfiguration
from nucypher.config.constants import BASE_DIR


def select_test_port() -> int:
    """
    Search for a network port that is open at the time of the call;
    Verify that the port is not the same as the default Ursula running port.

    Note: There is no guarantee that the returned port will still be available later.
    """

    closed_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    with contextlib.closing(closed_socket) as open_socket:
        open_socket.bind(('localhost', 0))
        port = open_socket.getsockname()[1]

        if port == UrsulaConfiguration.DEFAULT_REST_PORT:
            return select_test_port()

        open_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        return port


#
# Ursula
#

MOCK_URSULA_STARTING_PORT = select_test_port()

MOCK_KNOWN_URSULAS_CACHE = dict()

NUMBER_OF_URSULAS_IN_BLOCKCHAIN_TESTS = 10

NUMBER_OF_ETH_TEST_ACCOUNTS = NUMBER_OF_URSULAS_IN_BLOCKCHAIN_TESTS + 10

NUMBER_OF_URSULAS_IN_DEVELOPMENT_NETWORK = NUMBER_OF_URSULAS_IN_BLOCKCHAIN_TESTS


#
# Testerchain
#

TEST_CONTRACTS_DIR = os.path.join(BASE_DIR, 'tests', 'blockchain', 'eth', 'contracts', 'contracts')

MAX_TEST_SEEDER_ENTRIES = 20

ONE_YEAR_IN_SECONDS = ((60 * 60) * 24) * 365

DEVELOPMENT_TOKEN_AIRDROP_AMOUNT = NU(1_000_000, 'NU')

DEVELOPMENT_ETH_AIRDROP_AMOUNT = int(Web3().toWei(100, 'ether'))

NUMBER_OF_ALLOCATIONS_IN_TESTS = 100  # TODO: Move to constants


#
# Insecure Secrets
#

INSECURE_DEVELOPMENT_PASSWORD = ''.join(SystemRandom().choice(ascii_uppercase + digits) for _ in range(16))

STAKING_ESCROW_DEPLOYMENT_SECRET = INSECURE_DEVELOPMENT_PASSWORD + str(os.urandom(16))

POLICY_MANAGER_DEPLOYMENT_SECRET = INSECURE_DEVELOPMENT_PASSWORD + str(os.urandom(16))

USER_ESCROW_PROXY_DEPLOYMENT_SECRET = INSECURE_DEVELOPMENT_PASSWORD + str(os.urandom(16))

ADJUDICATOR_DEPLOYMENT_SECRET = INSECURE_DEVELOPMENT_PASSWORD + str(os.urandom(16))


#
# Temporary Directories and Files
#

BASE_TEMP_DIR = os.path.join('/', 'tmp')

BASE_TEMP_PREFIX = 'nucypher-tmp-'

MOCK_CUSTOM_INSTALLATION_PATH = os.path.join(BASE_TEMP_DIR, f'{BASE_TEMP_PREFIX}test-custom-{str(datetime.now())}')

MOCK_ALLOCATION_INFILE = os.path.join(BASE_TEMP_DIR, f'{BASE_TEMP_PREFIX}test-allocations-{str(datetime.now())}.json')

MOCK_ALLOCATION_REGISTRY_FILEPATH = os.path.join(BASE_TEMP_DIR, f'{BASE_TEMP_PREFIX}test-allocation-registry-{str(datetime.now())}.json')

MOCK_CUSTOM_INSTALLATION_PATH_2 = '/tmp/nucypher-tmp-test-custom-2-{}'.format(time.time())

MOCK_REGISTRY_FILEPATH = os.path.join(BASE_TEMP_DIR, f'{BASE_TEMP_PREFIX}mock-registry-{str(datetime.now())}.json')

TEMPORARY_DOMAIN = ':TEMPORARY_DOMAIN:'  # for use with `--dev` node runtimes

GETH_DEV_URI = f'ipc://{BASE_TEMP_DIR}/geth.ipc'  # Standard IPC path for `geth --dev`

PYEVM_DEV_URI = "tester://pyevm"

TEST_PROVIDER_URI = PYEVM_DEV_URI  # TODO: Pytest flag entry point?


#
# Node Configuration
#

MOCK_POLICY_DEFAULT_M = 3

MOCK_IP_ADDRESS = '0.0.0.0'

MOCK_IP_ADDRESS_2 = '10.10.10.10'

MOCK_URSULA_DB_FILEPATH = ':memory:'

#
# Gas
#

TEST_GAS_LIMIT = 8_500_000

PYEVM_GAS_LIMIT = TEST_GAS_LIMIT  # TODO: move elsewhere (used to set pyevm gas limit in tests)?

