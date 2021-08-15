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

import string
from datetime import datetime
from pathlib import Path

import tempfile
from random import SystemRandom
from web3 import Web3

from nucypher.blockchain.eth.token import NU
from nucypher.config.constants import NUCYPHER_ENVVAR_KEYSTORE_PASSWORD, NUCYPHER_ENVVAR_WORKER_ETH_PASSWORD

#
# Ursula
#

NUMBER_OF_URSULAS_IN_BLOCKCHAIN_TESTS = 10

NUMBER_OF_STAKERS_IN_BLOCKCHAIN_TESTS = NUMBER_OF_URSULAS_IN_BLOCKCHAIN_TESTS

# Ursulas (Workers) and Stakers have their own account
NUMBER_OF_ETH_TEST_ACCOUNTS = NUMBER_OF_URSULAS_IN_BLOCKCHAIN_TESTS + NUMBER_OF_STAKERS_IN_BLOCKCHAIN_TESTS + 10

NUMBER_OF_URSULAS_IN_DEVELOPMENT_NETWORK = NUMBER_OF_URSULAS_IN_BLOCKCHAIN_TESTS

#
# Local Signer Keystore
#

KEYFILE_NAME_TEMPLATE = 'UTC--2020-{month}-21T03-42-07.869432648Z--{address}'

MOCK_KEYSTORE_PATH = '/home/fakeMcfakeson/.ethereum/llamanet/keystore/'

MOCK_SIGNER_URI = f'keystore://{MOCK_KEYSTORE_PATH}'

NUMBER_OF_MOCK_KEYSTORE_ACCOUNTS = NUMBER_OF_ETH_TEST_ACCOUNTS


#
# Testerchain
#


ONE_YEAR_IN_SECONDS = ((60 * 60) * 24) * 365

DEVELOPMENT_TOKEN_AIRDROP_AMOUNT = NU(1_000_000, 'NU')

MIN_STAKE_FOR_TESTS = NU(750_000, 'NU').to_nunits()

BONUS_TOKENS_FOR_TESTS = NU(150_000, 'NU').to_nunits()

DEVELOPMENT_ETH_AIRDROP_AMOUNT = int(Web3().toWei(100, 'ether'))

NUMBER_OF_ALLOCATIONS_IN_TESTS = 50  # TODO: Move to constants


#
# Insecure Secrets
#

__valid_password_chars = string.ascii_uppercase + string.ascii_lowercase + string.digits

INSECURE_DEVELOPMENT_PASSWORD = ''.join(SystemRandom().choice(__valid_password_chars) for _ in range(32))

#
# Temporary Directories and Files
#

BASE_TEMP_DIR = Path(tempfile.gettempdir())

BASE_TEMP_PREFIX = 'nucypher-tmp-'

DATETIME_FORMAT = "%Y-%m-%d_%H-%M-%S.%f"

MOCK_CUSTOM_INSTALLATION_PATH = BASE_TEMP_DIR / f'{BASE_TEMP_PREFIX}test-custom-{datetime.now().strftime(DATETIME_FORMAT)}'

MOCK_CUSTOM_INSTALLATION_PATH_2 = BASE_TEMP_DIR / f'{BASE_TEMP_PREFIX}test-custom-2-{datetime.now().strftime(DATETIME_FORMAT)}'

MOCK_REGISTRY_FILEPATH = BASE_TEMP_DIR / f'{BASE_TEMP_PREFIX}mock-registry-{datetime.now().strftime(DATETIME_FORMAT)}.json'

GETH_DEV_URI = f'ipc://{BASE_TEMP_DIR}/geth.ipc'  # Standard IPC path for `geth --dev`

PYEVM_DEV_URI = "tester://pyevm"

TEST_PROVIDER_URI = PYEVM_DEV_URI  # TODO: Pytest flag entry point?

MOCK_PROVIDER_URI = 'tester://mock'

#
# Node Configuration
#

MOCK_POLICY_DEFAULT_THRESHOLD = 3

# These IP addresses are reserved for usage in documentation
# https://tools.ietf.org/html/rfc5737
MOCK_IP_ADDRESS = '192.0.2.100'
MOCK_IP_ADDRESS_2 = '203.0.113.20'

FEE_RATE_RANGE = (5, 10, 15)


#
# Gas
#

TEST_GAS_LIMIT = 8_000_000  # gas

PYEVM_GAS_LIMIT = TEST_GAS_LIMIT  # TODO: move elsewhere (used to set pyevm gas limit in tests)?


#
# CLI
#

YES = 'Y'
YES_ENTER = YES + '\n'

NO = 'N'
NO_ENTER = NO + '\n'

FAKE_PASSWORD_CONFIRMED = '{password}\n{password}\n'.format(password=INSECURE_DEVELOPMENT_PASSWORD)

CLI_TEST_ENV = {NUCYPHER_ENVVAR_KEYSTORE_PASSWORD: INSECURE_DEVELOPMENT_PASSWORD}

CLI_ENV = {NUCYPHER_ENVVAR_KEYSTORE_PASSWORD: INSECURE_DEVELOPMENT_PASSWORD,
           NUCYPHER_ENVVAR_WORKER_ETH_PASSWORD: INSECURE_DEVELOPMENT_PASSWORD}
