import string
import tempfile
from datetime import datetime
from pathlib import Path
from random import SystemRandom

from web3 import Web3

from nucypher.blockchain.eth.token import NU
from nucypher.config.constants import (
    NUCYPHER_ENVVAR_KEYSTORE_PASSWORD,
    NUCYPHER_ENVVAR_OPERATOR_ETH_PASSWORD,
)

#
#  Contracts
#


MOCK_STAKING_CONTRACT_NAME = 'ThresholdStakingForPREApplicationMock'

#
# Ursula
#

NUMBER_OF_URSULAS_IN_BLOCKCHAIN_TESTS = 16

NUMBER_OF_STAKING_PROVIDERS_IN_BLOCKCHAIN_TESTS = NUMBER_OF_URSULAS_IN_BLOCKCHAIN_TESTS

# Ursulas (Operators) and Staking Providers have their own account
NUMBER_OF_ETH_TEST_ACCOUNTS = NUMBER_OF_URSULAS_IN_BLOCKCHAIN_TESTS + NUMBER_OF_STAKING_PROVIDERS_IN_BLOCKCHAIN_TESTS + 10

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

MIN_STAKE_FOR_TESTS = NU(750_000, 'NU').to_units()

BONUS_TOKENS_FOR_TESTS = NU(150_000, 'NU').to_units()

DEVELOPMENT_ETH_AIRDROP_AMOUNT = int(Web3().to_wei(100, 'ether'))

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

TEST_ETH_PROVIDER_URI = PYEVM_DEV_URI  # TODO: Pytest flag entry point?

TEST_POLYGON_PROVIDER_URI = "tester://polygon"

MOCK_ETH_PROVIDER_URI = 'tester://mock'

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
           NUCYPHER_ENVVAR_OPERATOR_ETH_PASSWORD: INSECURE_DEVELOPMENT_PASSWORD}
TESTERCHAIN_CHAIN_ID = 131277322940537


#
# Network
#

RPC_TOO_MANY_REQUESTS = {
    "jsonrpc": "2.0",
    "error": {
        "code": 429,
        "message": "Too many concurrent requests"
    }
}

RPC_SUCCESSFUL_RESPONSE = {
    "jsonrpc": "2.0",
    "id": 1,
    "result": "Geth/v1.9.20-stable-979fc968/linux-amd64/go1.15"
}


FAKE_TRANSCRIPT = b'\x98\x00\x00\x00\x00\x00\x00\x00\x03\x00\x00\x00\x00\x00\x00\x00\xae\xdb_-\xeaj\x9bz\xdd\xd6\x98\xf8\xf91A\xc1\x8f;\x13@\x89\xcb\xcf>\x86\xc4T\xfb\x0c\x1ety\x8b\xd8mSkk\xbb\xcaU\xe5]v}E\xfa\xbc\xae\xb6\xa1\xf4e\x19\x86\xf2L\xcaZj\x03]h:\xbfP\x03Q\x8c\x95e\xe0c\xaa\xc2\xb4\xbby}\xecW%\xdet\xc8\xfc\xe7ky\xe5\xf6\xe9\xf5\x05\xe5\xdf\x81\x9bx\x18\xa4\x15\x85\xdeA9\x9f\x99\xceQ\xb0\xd0&\x9a\xa7\xaed&\x99\xdc\xa7\xfeLM\x01\x02\x87\xc8\x14$\x89"kA\x0b\x91\t\x1e\x1c/f\x00N,\x88\x01\x00\x00\x00\x00\x00\x00\x04\x00\x00\x00\x00\x00\x00\x00\xab\x0f\tFA\xdcB\xd4\xb3\x08\xd7IVkmw6za\xb6)\x13\x014]f.\xa1\xcd\xe27\xee\xc0\x95\xf6\xa4\x12\xa9\x19\x94\xed\x05\xffF\x81\xb2\xb2\xcb\x06\xaf-\xe4\xb5\x98\xbd\x81\x0f\xb8\xb7\xa1<\xf6/\xe5\xa4\x11\x83}\xfaH\x15\x80h\n\xe7\xc6\xc2\xb3\xd5{dH\xeb\x1e]v\xb4\x88v\x88\xb7N1\xff\x80\xd0\x88\x04.\x00\x82K\x1e\x96\xa0\xbd}X\xbb{?6\xeb\xe7\rg\x03\xeeG\x01\x10^\xee\x9cH\x94[\x9d8s\xa3\xb6\x8f\xfc\xf1\xdf\x01m\xf9\x08_N\xb5-\x16O\x89n\x95\xf3\x8b[\x1f&Yk?*\x07\x8fQ\x98\x85\xd5\xc1YL\xe0CB\xb2"!\x8d,\x90Q7\xca\x9c\x0e\xb2\x7f\xb0\xe1\xc8\xdd\xe7\xe1\xe4\x14\xb3\xa6\xb4\x8e\x8b\xed\xacM\xc3\x9d\xc4|U\x93k\x17\xac\x14\x86\x16\xd7\xebk\xbd{\xad}\x87\x13Y\x83\x9d\x88\x1e\x1b4\xa7r\xa6\x80\xbf\xf0\x15\x99\x11Q\xdb\xeb\xdf\x15ns\xc6\x85\xb3\x1d\xf5j\xc5\x87`=OD\x86\x86\x08\x8d\xb6\x0b\xec\x1d\x15\xc9\x93\x9a\xed\xa3\xe2\x96\xa4\xa2b\xa6\xa5h\xb0\xbb4\xb3\x0c\xa5\xdcu\x1f{\xb9\xaf\xd0W\xe1\xa3&\xa8\xb5\xea\xe5c\xfd\xc7?\xbdLg\xb3\xae\xb9\xb8*\xfc\xd5\xa6\xeeI\x15v\xdc\xa2`1VZ\xb5\x1c_`\x86\xbe{\xef\xae\t\xf2\xa9N\x00\x9a\xa1F\x84\xb2\xe3\xbc\xfa\xf7I\xee\xe8[~\x99;i\xfc%\xa8\x80\x80\x8e%\'\x9c+\x9c\xa9\x13R!\x80w\xc0\xda[\x84\xf6X\xfe\xc2\xe3\x0f\x94-\xbb`\x00\x00\x00\x00\x00\x00\x00\x93\xff\x1e\x1b\x15;e\xfe}\x83v K\xf9\r\xc9\xad\x9d\xddN\xcd\xcaWq\xfa\x8e\x98sn\x9b~t\x01 =p\xe5\xb1\x7f"!\xb4\xb9\xc9W\x90\x86\x80\x17\nm\xa0\x8dD\xb5\xaf\xfc\xa5\xf5%V]\xb9\x89a@\xe5\x0c@#%x\xecW\xed\xb0a\x98\x1a!C\x80B@{\xf0\xffJ{\xa3\xeayDP\'u'
