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

from nucypher.blockchain.eth.constants import DISPATCHER_SECRET_LENGTH, NUNITS_PER_TOKEN
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


MOCK_POLICY_DEFAULT_M = 3

MOCK_URSULA_STARTING_PORT = select_test_port()

MOCK_KNOWN_URSULAS_CACHE = {}

NUMBER_OF_URSULAS_IN_DEVELOPMENT_NETWORK = 10


#
# Testerchain
#

TEST_CONTRACTS_DIR = os.path.join(BASE_DIR, 'tests', 'blockchain', 'eth', 'contracts', 'contracts')

DEVELOPMENT_TOKEN_AIRDROP_AMOUNT = 1000000 * int(NUNITS_PER_TOKEN)

DEVELOPMENT_ETH_AIRDROP_AMOUNT = 10 ** 6 * 10 ** 18  # wei -> ether

MINERS_ESCROW_DEPLOYMENT_SECRET = os.urandom(DISPATCHER_SECRET_LENGTH)

POLICY_MANAGER_DEPLOYMENT_SECRET = os.urandom(DISPATCHER_SECRET_LENGTH)

INSECURE_DEVELOPMENT_PASSWORD = ''.join(SystemRandom().choice(ascii_uppercase + digits) for _ in range(16))

MAX_TEST_SEEDER_ENTRIES = 20

TESTING_ETH_AIRDROP_AMOUNT = int(Web3().fromWei(100, 'ether'))


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

TEMPORARY_DOMAIN = b':TEMPORARY_DOMAIN:'  # for use with `--dev` node runtimes

GETH_DEV_URI = f'ipc://{BASE_TEMP_DIR}/geth.ipc'  # Standard IPC path for `geth --dev`

PYEVM_DEV_URI = "tester://pyevm"

TEST_PROVIDER_URI = PYEVM_DEV_URI  # TODO: Pytest flag entry point?


#
# Node Configuration
#

MOCK_IP_ADDRESS = '0.0.0.0'

MOCK_IP_ADDRESS_2 = '10.10.10.10'

MOCK_URSULA_DB_FILEPATH = ':memory:'

PYEVM_GAS_LIMIT = 6500000  # TODO: move elsewhere (used to set pyevm gas limit in tests)?