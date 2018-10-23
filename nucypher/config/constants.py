from collections import namedtuple
from os.path import abspath, dirname

from appdirs import AppDirs

import nucypher

# Base Filepaths
BASE_DIR = abspath(dirname(dirname(nucypher.__file__)))
PROJECT_ROOT = abspath(dirname(nucypher.__file__))
APP_DIR = AppDirs("nucypher", "NuCypher")
DEFAULT_CONFIG_ROOT = APP_DIR.user_data_dir

#
# seednodes
#
SeednodeMetadata = namedtuple('seednode', ['checksum_address', 'rest_host', 'rest_port'])
SEEDNODES = (
    SeednodeMetadata('0xDbf2Bc4b81eB46CdDfa52348Ecf3c142841267E0', 'https://18.223.117.103', '9151'),
)

