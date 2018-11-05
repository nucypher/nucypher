from collections import namedtuple
from os.path import abspath, dirname

from appdirs import AppDirs

import nucypher

PACKAGE_NAME = 'nucypher'

# Base Filepaths
BASE_DIR = abspath(dirname(dirname(nucypher.__file__)))
PROJECT_ROOT = abspath(dirname(nucypher.__file__))
APP_DIR = AppDirs(PACKAGE_NAME, "NuCypher")
DEFAULT_CONFIG_ROOT = APP_DIR.user_data_dir

# Static Seednodes
SeednodeMetadata = namedtuple('seednode', ['checksum_address', 'rest_host', 'rest_port'])
SEEDNODES = tuple()

# Sentry (Set to False to disable sending Errors and Logs to NuCypher's Sentry.)
REPORT_TO_SENTRY = True
NUCYPHER_SENTRY_ENDPOINT = "https://d8af7c4d692e4692a455328a280d845e@sentry.io/1310685"

# CLI
DEBUG = True
KEYRING_PASSPHRASE_ENVVAR_KEY = 'NUCYPHER_KEYRING_PASSPHRASE'
