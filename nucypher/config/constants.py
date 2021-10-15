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


from collections import namedtuple
from pathlib import Path

import os
from appdirs import AppDirs

from maya import MayaDT

import nucypher

# Environment variables
NUCYPHER_ENVVAR_KEYRING_PASSWORD = "NUCYPHER_KEYRING_PASSWORD"
NUCYPHER_ENVVAR_WORKER_ADDRESS = "NUCYPHER_WORKER_ADDRESS"
NUCYPHER_ENVVAR_WORKER_ETH_PASSWORD = "NUCYPHER_WORKER_ETH_PASSWORD"
NUCYPHER_ENVVAR_ALICE_ETH_PASSWORD = "NUCYPHER_ALICE_ETH_PASSWORD"
NUCYPHER_ENVVAR_BOB_ETH_PASSWORD = "NUCYPHER_BOB_ETH_PASSWORD"
NUCYPHER_ENVVAR_PROVIDER_URI = "NUCYPHER_PROVIDER_URI"

# Base Filepaths
NUCYPHER_PACKAGE = Path(nucypher.__file__).parent.resolve()
BASE_DIR = NUCYPHER_PACKAGE.parent.resolve()
DEPLOY_DIR = BASE_DIR / 'deploy'
NUCYPHER_TEST_DIR = BASE_DIR / 'tests'

# User Application Filepaths
APP_DIR = AppDirs(nucypher.__title__, nucypher.__author__)
DEFAULT_CONFIG_ROOT = os.getenv('NUCYPHER_CONFIG_ROOT', default=APP_DIR.user_data_dir)
USER_LOG_DIR = os.getenv('NUCYPHER_USER_LOG_DIR', default=APP_DIR.user_log_dir)
DEFAULT_LOG_FILENAME = "nucypher.log"
DEFAULT_JSON_LOG_FILENAME = "nucypher.json"


# Static Seednodes
SeednodeMetadata = namedtuple('seednode', ['checksum_address', 'rest_host', 'rest_port'])
SEEDNODES = tuple()


# Sentry (Add your public key and user ID below)
NUCYPHER_SENTRY_PUBLIC_KEY = ""
NUCYPHER_SENTRY_USER_ID = ""
NUCYPHER_SENTRY_ENDPOINT = f"https://{NUCYPHER_SENTRY_PUBLIC_KEY}@sentry.io/{NUCYPHER_SENTRY_USER_ID}"


# Web
CLI_ROOT = NUCYPHER_PACKAGE / 'network' / 'templates'
TEMPLATES_DIR = CLI_ROOT / 'templates'
MAX_UPLOAD_CONTENT_LENGTH = 1024 * 50


# Dev Mode
TEMPORARY_DOMAIN = ":temporary-domain:"  # for use with `--dev` node runtimes


# Event Blocks Throttling
NUCYPHER_EVENTS_THROTTLE_MAX_BLOCKS = 'NUCYPHER_EVENTS_THROTTLE_MAX_BLOCKS'

# Probationary period (see #2353, #2584)
END_OF_POLICIES_PROBATIONARY_PERIOD = MayaDT.from_iso8601('2021-12-31T23:59:59.0Z')
