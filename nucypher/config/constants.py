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
PROJECT_ROOT = abspath(dirname(nucypher.__file__))
CONTRACT_ROOT = os.path.join(abspath(dirname(sol.__file__)), 'source', 'contracts')


# User Application Filepaths
APP_DIR = AppDirs(nucypher.__title__, nucypher.__author__)
DEFAULT_CONFIG_ROOT = APP_DIR.user_data_dir
USER_LOG_DIR = APP_DIR.user_log_dir


# Static Seednodes
SeednodeMetadata = namedtuple('seednode', ['checksum_public_address', 'rest_host', 'rest_port'])
SEEDNODES = tuple()


# Domains
"""
If this domain is among those being learned or served, then domain checking is skipped.
A Learner learning about the GLOBAL_DOMAIN will learn about all nodes.
A Teacher serving the GLOBAL_DOMAIN will teach about all nodes.
"""
GLOBAL_DOMAIN = b'GLOBAL_DOMAIN'

# Sentry
NUCYPHER_SENTRY_ENDPOINT = "https://d8af7c4d692e4692a455328a280d845e@sentry.io/1310685"  # TODO: Use nucypher DNS domain

# Web
TEMPLATES_DIR = os.path.join(abspath(dirname(cli.__file__)), 'templates')
