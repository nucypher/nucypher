import os
from os.path import abspath, dirname

from appdirs import AppDirs

import nucypher

#
# Base Filepaths
#
BASE_DIR = abspath(dirname(dirname(nucypher.__file__)))
PROJECT_ROOT = abspath(dirname(nucypher.__file__))
APP_DIR = AppDirs("nucypher", "NuCypher")

#
# Configuration File
#
DEFAULT_CONFIG_ROOT = APP_DIR.user_data_dir

#
# Test Constants  # TODO: Tidy up filepath here
#
TEST_CONTRACTS_DIR = os.path.join(BASE_DIR, 'tests', 'blockchain', 'eth', 'contracts', 'contracts')
NUMBER_OF_URSULAS_IN_MOCK_NETWORK = 10
