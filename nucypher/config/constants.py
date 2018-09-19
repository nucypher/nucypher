import os
from os.path import abspath, dirname

from appdirs import AppDirs

import nucypher

# Base Filepaths
BASE_DIR = abspath(dirname(dirname(nucypher.__file__)))
PROJECT_ROOT = abspath(dirname(nucypher.__file__))
APP_DIR = AppDirs("nucypher", "NuCypher")

# Configuration File
TEMPLATE_CONFIG_FILE_LOCATION = os.path.join(BASE_DIR, 'cli', '.nucypher.ini')
DEFAULT_CONFIG_ROOT = APP_DIR.user_data_dir
DEFAULT_CONFIG_FILE_LOCATION = os.path.join(DEFAULT_CONFIG_ROOT, 'nucypher.ini')

# Test Constants
test_contract_dir = os.path.join(BASE_DIR, 'tests', 'blockchain', 'eth', 'contracts', 'contracts')
TEST_CONTRACTS_DIR = test_contract_dir

NUMBER_OF_TEST_ETH_ACCOUNTS = 10
NUMBER_OF_URSULAS_IN_FAKE_NETWORK = NUMBER_OF_TEST_ETH_ACCOUNTS
