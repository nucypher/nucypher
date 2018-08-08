"""Nucypher configuration defaults"""


import os
from os.path import dirname, abspath

from appdirs import AppDirs

import nucypher

APP_DIRS = AppDirs("nucypher", "NuCypher")
PROJECT_ROOT = abspath(dirname(nucypher.__file__))

DEFAULT_CONFIG_ROOT = APP_DIRS.user_data_dir
DEFAULT_INI_FILEPATH = os.path.join(DEFAULT_CONFIG_ROOT, 'nucypher.ini')
DEFAULT_KEYRING_ROOT = os.path.join(DEFAULT_CONFIG_ROOT, 'keyring')
DEFAULT_SIMULATION_REGISTRY_FILEPATH = os.path.join(DEFAULT_CONFIG_ROOT, 'simulation_registry.json')
DEFAULT_SIMULATION_PORT = 5555

DEFAULT_SEED_NODE_DIR = os.path.join(DEFAULT_CONFIG_ROOT, 'seed_nodes')
DEFAULT_KNOWN_NODE_DIR = os.path.join(DEFAULT_CONFIG_ROOT, 'known_nodes')
