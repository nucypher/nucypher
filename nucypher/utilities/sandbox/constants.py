"""
This file is part of nucypher.

nucypher is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

nucypher is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with nucypher.  If not, see <https://www.gnu.org/licenses/>.
"""


import contextlib
import os
import time

import socket

from nucypher.blockchain.eth.constants import DISPATCHER_SECRET_LENGTH, M
from nucypher.config.characters import UrsulaConfiguration


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

DEVELOPMENT_TOKEN_AIRDROP_AMOUNT = 1000000 * int(M)

DEVELOPMENT_ETH_AIRDROP_AMOUNT = 10 ** 6 * 10 ** 18  # wei -> ether

MINERS_ESCROW_DEPLOYMENT_SECRET = os.urandom(DISPATCHER_SECRET_LENGTH)

POLICY_MANAGER_DEPLOYMENT_SECRET = os.urandom(DISPATCHER_SECRET_LENGTH)

INSECURE_DEVELOPMENT_PASSWORD = 'this-is-not-a-secure-password'

MAX_TEST_SEEDER_ENTRIES = 20

MOCK_IP_ADDRESS = '0.0.0.0'

MOCK_IP_ADDRESS_2 = '10.10.10.10'

MOCK_URSULA_DB_FILEPATH = ':memory:'

MOCK_CUSTOM_INSTALLATION_PATH = '/tmp/nucypher-tmp-test-custom-{}'.format(time.time())

MOCK_CUSTOM_INSTALLATION_PATH_2 = '/tmp/nucypher-tmp-test-custom-2-{}'.format(time.time())

