import os
from collections import namedtuple
from pathlib import Path

from appdirs import AppDirs
from maya import MayaDT

import nucypher

# Environment variables
NUCYPHER_ENVVAR_KEYSTORE_PASSWORD = "NUCYPHER_KEYSTORE_PASSWORD"
NUCYPHER_ENVVAR_OPERATOR_ADDRESS = "NUCYPHER_OPERATOR_ADDRESS"
NUCYPHER_ENVVAR_OPERATOR_ETH_PASSWORD = "NUCYPHER_OPERATOR_ETH_PASSWORD"
NUCYPHER_ENVVAR_ALICE_ETH_PASSWORD = "NUCYPHER_ALICE_ETH_PASSWORD"
NUCYPHER_ENVVAR_BOB_ETH_PASSWORD = "NUCYPHER_BOB_ETH_PASSWORD"

NUCYPHER_ENVVAR_STAKING_PROVIDERS_PAGINATION_SIZE_LIGHT_NODE = "NUCYPHER_STAKING_PROVIDERS_PAGINATION_SIZE_LIGHT_NODE"
NUCYPHER_ENVVAR_STAKING_PROVIDERS_PAGINATION_SIZE = "NUCYPHER_STAKING_PROVIDERS_PAGINATION_SIZE"

# Base Filepaths
NUCYPHER_PACKAGE = Path(nucypher.__file__).parent.resolve()
BASE_DIR = NUCYPHER_PACKAGE.parent.resolve()

# User Application Filepaths
APP_DIR = AppDirs(nucypher.__title__, nucypher.__author__)
DEFAULT_CONFIG_ROOT = Path(os.getenv('NUCYPHER_CONFIG_ROOT', default=APP_DIR.user_data_dir))
USER_LOG_DIR = Path(os.getenv('NUCYPHER_USER_LOG_DIR', default=APP_DIR.user_log_dir))
DEFAULT_LOG_FILENAME = "nucypher.log"
DEFAULT_JSON_LOG_FILENAME = "nucypher.json"

# Static Seednodes
SeednodeMetadata = namedtuple('seednode', ['checksum_address', 'rest_host', 'rest_port'])

# Sentry (Add your public key and user ID below)
NUCYPHER_SENTRY_PUBLIC_KEY = ""
NUCYPHER_SENTRY_USER_ID = ""
NUCYPHER_SENTRY_ENDPOINT = f"https://{NUCYPHER_SENTRY_PUBLIC_KEY}@sentry.io/{NUCYPHER_SENTRY_USER_ID}"

# Web
CLI_ROOT = NUCYPHER_PACKAGE / "network" / "templates"
MAX_UPLOAD_CONTENT_LENGTH = 1024 * 250  # 250kb

# Dev Mode
TEMPORARY_DOMAIN_NAME = ":temporary-domain:"  # for use with `--dev` node runtimes

# Event Blocks Throttling
NUCYPHER_EVENTS_THROTTLE_MAX_BLOCKS = 'NUCYPHER_EVENTS_THROTTLE_MAX_BLOCKS'

# Probationary period
END_OF_POLICIES_PROBATIONARY_PERIOD = MayaDT.from_iso8601('2023-4-20T23:59:59.0Z')
