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
import string
import tempfile
import time
from datetime import datetime
from random import SystemRandom

from web3 import Web3

from nucypher.blockchain.eth.token import NU
from nucypher.config.characters import UrsulaConfiguration
from nucypher.config.constants import BASE_DIR
from nucypher.crypto.api import keccak_digest


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

NUMBER_OF_STAKERS_IN_BLOCKCHAIN_TESTS = NUMBER_OF_URSULAS_IN_BLOCKCHAIN_TESTS

# Ursulas (Workers) and Stakers have their own account
NUMBER_OF_ETH_TEST_ACCOUNTS = NUMBER_OF_URSULAS_IN_BLOCKCHAIN_TESTS + NUMBER_OF_STAKERS_IN_BLOCKCHAIN_TESTS + 10

NUMBER_OF_URSULAS_IN_DEVELOPMENT_NETWORK = NUMBER_OF_URSULAS_IN_BLOCKCHAIN_TESTS


#
# Testerchain
#

TEST_CONTRACTS_DIR = os.path.join(BASE_DIR, 'tests', 'blockchain', 'eth', 'contracts', 'contracts')

MAX_TEST_SEEDER_ENTRIES = 20

ONE_YEAR_IN_SECONDS = ((60 * 60) * 24) * 365

DEVELOPMENT_TOKEN_AIRDROP_AMOUNT = NU(1_000_000, 'NU')

MIN_STAKE_FOR_TESTS = NU(750_000, 'NU').to_nunits()

BONUS_TOKENS_FOR_TESTS = NU(150_000, 'NU').to_nunits()

DEVELOPMENT_ETH_AIRDROP_AMOUNT = int(Web3().toWei(100, 'ether'))

NUMBER_OF_ALLOCATIONS_IN_TESTS = 100  # TODO: Move to constants


#
# Insecure Secrets
#

__valid_password_chars = string.ascii_uppercase + string.ascii_lowercase + string.digits

INSECURE_DEVELOPMENT_PASSWORD = ''.join(SystemRandom().choice(__valid_password_chars) for _ in range(16))

STAKING_ESCROW_DEPLOYMENT_SECRET = INSECURE_DEVELOPMENT_PASSWORD + str(os.urandom(16))

POLICY_MANAGER_DEPLOYMENT_SECRET = INSECURE_DEVELOPMENT_PASSWORD + str(os.urandom(16))

STAKING_INTERFACE_DEPLOYMENT_SECRET = INSECURE_DEVELOPMENT_PASSWORD + str(os.urandom(16))

ADJUDICATOR_DEPLOYMENT_SECRET = INSECURE_DEVELOPMENT_PASSWORD + str(os.urandom(16))

INSECURE_DEPLOYMENT_SECRET_PLAINTEXT = bytes(''.join(SystemRandom().choice(__valid_password_chars) for _ in range(16)), encoding='utf-8')

INSECURE_DEPLOYMENT_SECRET_HASH = keccak_digest(INSECURE_DEPLOYMENT_SECRET_PLAINTEXT)


#
# Temporary Directories and Files
#

BASE_TEMP_DIR = tempfile.gettempdir()

BASE_TEMP_PREFIX = 'nucypher-tmp-'
DATETIME_FORMAT = "%Y-%m-%d_%H-%M-%S.%f"

MOCK_CUSTOM_INSTALLATION_PATH = os.path.join(BASE_TEMP_DIR, f'{BASE_TEMP_PREFIX}test-custom-{datetime.now().strftime(DATETIME_FORMAT)}')

MOCK_ALLOCATION_INFILE = os.path.join(BASE_TEMP_DIR, f'{BASE_TEMP_PREFIX}test-allocations-{datetime.now().strftime(DATETIME_FORMAT)}.json')

MOCK_ALLOCATION_REGISTRY_FILEPATH = os.path.join(BASE_TEMP_DIR, f'{BASE_TEMP_PREFIX}test-allocation-registry-{datetime.now().strftime(DATETIME_FORMAT)}.json')

MOCK_INDIVIDUAL_ALLOCATION_FILEPATH = os.path.join(BASE_TEMP_DIR, f'{BASE_TEMP_PREFIX}test-individual-allocation-{datetime.now().strftime(DATETIME_FORMAT)}.json')

MOCK_CUSTOM_INSTALLATION_PATH_2 = '/tmp/nucypher-tmp-test-custom-2-{}'.format(time.time())

MOCK_REGISTRY_FILEPATH = os.path.join(BASE_TEMP_DIR, f'{BASE_TEMP_PREFIX}mock-registry-{datetime.now().strftime(DATETIME_FORMAT)}.json')

TEMPORARY_DOMAIN = ":TEMPORARY_DOMAIN:"  # for use with `--dev` node runtimes and tests

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

TEST_GAS_LIMIT = 8_000_000  # gas

PYEVM_GAS_LIMIT = TEST_GAS_LIMIT  # TODO: move elsewhere (used to set pyevm gas limit in tests)?

