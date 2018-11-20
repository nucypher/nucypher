"""
This file is part of nucypher.

nucypher is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

nucypher is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with nucypher.  If not, see <https://www.gnu.org/licenses/>.
"""


from collections import namedtuple
from os.path import abspath, dirname

from appdirs import AppDirs

import nucypher


# Base Filepaths
BASE_DIR = abspath(dirname(dirname(nucypher.__file__)))
PROJECT_ROOT = abspath(dirname(nucypher.__file__))

# User Application Filepaths
APP_DIR = AppDirs(nucypher.__title__, nucypher.__author__)
DEFAULT_CONFIG_ROOT = APP_DIR.user_data_dir
USER_LOG_DIR = APP_DIR.user_log_dir

# Static Seednodes
SeednodeMetadata = namedtuple('seednode', ['checksum_address', 'rest_host', 'rest_port'])
SEEDNODES = tuple()
