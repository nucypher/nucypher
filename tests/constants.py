import string
import tempfile
from datetime import datetime
from pathlib import Path
from random import SystemRandom

from hexbytes import HexBytes
from web3 import Web3

from nucypher.blockchain.eth.token import NU
from nucypher.config.constants import (
    NUCYPHER_ENVVAR_KEYSTORE_PASSWORD,
    NUCYPHER_ENVVAR_OPERATOR_ETH_PASSWORD,
)

#
#  Contracts
#


MOCK_STAKING_CONTRACT_NAME = "ThresholdStakingForTACoApplicationMock"
RITUAL_TOKEN = "RitualToken"
T_TOKEN = "TToken"
TACO_CHILD_APPLICATION = "TACoChildApplication"
CONDITION_NFT = "ConditionNFT"
GLOBAL_ALLOW_LIST = "GlobalAllowList"


#
# Ursula
#

NUMBER_OF_URSULAS_IN_BLOCKCHAIN_TESTS = 10

NUMBER_OF_STAKING_PROVIDERS_IN_BLOCKCHAIN_TESTS = NUMBER_OF_URSULAS_IN_BLOCKCHAIN_TESTS

# Ursulas (Operators) and Staking Providers have their own account
NUMBER_OF_ETH_TEST_ACCOUNTS = NUMBER_OF_URSULAS_IN_BLOCKCHAIN_TESTS + NUMBER_OF_STAKING_PROVIDERS_IN_BLOCKCHAIN_TESTS + 10

NUMBER_OF_URSULAS_IN_DEVELOPMENT_DOMAIN = NUMBER_OF_URSULAS_IN_BLOCKCHAIN_TESTS

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

TESTERCHAIN_CHAIN_ID = 131277322940537


#
# Insecure Secrets
#

__valid_password_chars = string.ascii_uppercase + string.ascii_lowercase + string.digits

INSECURE_DEVELOPMENT_PASSWORD = ''.join(SystemRandom().choice(__valid_password_chars) for _ in range(32))

#
# Known Enrico signer
#

# private key for wallet address '0x070a85eD1Ddb44ecD07e746235bE0B959ff5b30A'
DEFAULT_TEST_ENRICO_PRIVATE_KEY = HexBytes(
    "0x900edb9e8214b2353f82aa195e915128f419a92cfb8bbc0f4784f10ef4112b86"
)

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

TEST_POLYGON_PROVIDER_URI = PYEVM_DEV_URI  # TODO: Introduce multichain separation tests

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
# Configuration
#

MIN_OPERATOR_SECONDS = 60 * 60 * 24  # one day in seconds


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
