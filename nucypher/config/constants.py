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
DEFAULT_CONFIG_ROOT = os.getenv('NUCYPHER_CONFIG_ROOT') or APP_DIR.user_data_dir
USER_LOG_DIR = APP_DIR.user_log_dir


# Static Seednodes (Not from seeder contract)
SeednodeMetadata = namedtuple('seednode', ['checksum_public_address', 'rest_host', 'rest_port'])
SEEDNODES = tuple()


"""
=======
DOMAINS
=======

If this domain is among those being learned or served, then domain checking is skipped.
A Learner learning about the GLOBAL_DOMAIN will learn about all nodes.
A Teacher serving the GLOBAL_DOMAIN will teach about all nodes.
"""

# Sentry
NUCYPHER_SENTRY_PUBLIC_KEY = "d8af7c4d692e4692a455328a280d845e"
NUCYPHER_SENTRY_USER_ID = '1310685'
NUCYPHER_SENTRY_ENDPOINT = f"https://{NUCYPHER_SENTRY_PUBLIC_KEY}@sentry.io/{NUCYPHER_SENTRY_USER_ID}"

# Web
TEMPLATES_DIR = os.path.join(abspath(dirname(cli.__file__)), 'templates')

# export NUCYPHER_CORS_ORIGINS=example.com,localhost,192.168.2.5:8080
CORS_ORIGINS = os.getenv('NUCYPHER_CORS_ORIGINS', '').split(',') or [
    "127.0.0.1:8080",
    "localhost:8080"
]

# https://developers.google.com/recaptcha/docs/v3
RECAPTCHA_SERVER_SECRET = os.getenv('NUCYPHER_RECATCHA_SECRET')

# given to trusted clients to allow them to bypass the captcha
FELIX_REGISTER_API_KEY = os.getenv('NUCYPHER_FELIX_REGISTER_API_KEY')
