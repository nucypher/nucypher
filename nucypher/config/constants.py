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

import os
from appdirs import AppDirs
from pathlib import Path

import nucypher
from nucypher.blockchain.eth import sol

# Environment variables
NUCYPHER_ENVVAR_KEYRING_PASSWORD = "NUCYPHER_KEYRING_PASSWORD"
NUCYPHER_ENVVAR_WORKER_ADDRESS = "NUCYPHER_WORKER_ADDRESS"
NUCYPHER_ENVVAR_WORKER_ETH_PASSWORD = "NUCYPHER_WORKER_ETH_PASSWORD"
NUCYPHER_ENVVAR_ALICE_ETH_PASSWORD = "NUCYPHER_ALICE_ETH_PASSWORD"
NUCYPHER_ENVVAR_PROVIDER_URI = "NUCYPHER_PROVIDER_URI"
NUCYPHER_ENVVAR_WORKER_IP_ADDRESS = 'NUCYPHER_WORKER_IP_ADDRESS'


# Base Filepaths
NUCYPHER_PACKAGE = Path(nucypher.__file__).parent.resolve()
BASE_DIR = NUCYPHER_PACKAGE.parent.resolve()
DEPLOY_DIR = BASE_DIR / 'deploy'
SOL_PACKAGE = Path(sol.__file__).parent.resolve()
CONTRACT_ROOT = SOL_PACKAGE / 'source' / 'contracts'


# User Application Filepaths
APP_DIR = AppDirs(nucypher.__title__, nucypher.__author__)
DEFAULT_CONFIG_ROOT = os.getenv('NUCYPHER_CONFIG_ROOT', default=APP_DIR.user_data_dir)
USER_LOG_DIR = os.getenv('NUCYPHER_USER_LOG_DIR', default=APP_DIR.user_log_dir)


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
TEMPLATES_DIR = os.path.join(abspath(dirname(cli.__file__)), 'templates')
STATICS_DIR = os.getenv('NUCYPHER_STATICS_DIR') or os.path.join(
     abspath(dirname(cli.__file__)), 'statics')
MAX_UPLOAD_CONTENT_LENGTH = 1024 * 50

# Dev Mode
TEMPORARY_DOMAIN = ":TEMPORARY_DOMAIN:"  # for use with `--dev` node runtimes
