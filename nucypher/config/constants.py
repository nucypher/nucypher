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


import os
from collections import namedtuple
from os.path import abspath, dirname

from appdirs import AppDirs

import nucypher
from nucypher import cli
from nucypher.blockchain.eth import sol


# Base Filepaths
BASE_DIR = abspath(dirname(dirname(nucypher.__file__)))
DEPLOY_DIR = os.path.join(BASE_DIR, 'deploy')
PROJECT_ROOT = abspath(dirname(nucypher.__file__))
CONTRACT_ROOT = os.path.join(abspath(dirname(sol.__file__)), 'source', 'contracts')


# User Application Filepaths
APP_DIR = AppDirs(nucypher.__title__, nucypher.__author__)
DEFAULT_CONFIG_ROOT = os.getenv('NUCYPHER_CONFIG_ROOT', default=APP_DIR.user_data_dir)
USER_LOG_DIR = os.getenv('NUCYPHER_USER_LOG_DIR', default=APP_DIR.user_log_dir)


# Static Seednodes (Not from seeder contract)
SeednodeMetadata = namedtuple('seednode', ['checksum_address', 'rest_host', 'rest_port'])
SEEDNODES = tuple()

# Sentry
NUCYPHER_SENTRY_PUBLIC_KEY = "fd21c3edda324065a34d3f334dddf1f0"
NUCYPHER_SENTRY_USER_ID = '1480080'
NUCYPHER_SENTRY_ENDPOINT = f"https://{NUCYPHER_SENTRY_PUBLIC_KEY}@sentry.io/{NUCYPHER_SENTRY_USER_ID}"

# Web
TEMPLATES_DIR = os.path.join(abspath(dirname(cli.__file__)), 'templates')
