"""Nucypher configuration defaults"""


import os
from os.path import dirname, abspath

from appdirs import AppDirs

import nucypher

BASE_DIR = abspath(dirname(dirname(nucypher.__file__)))

APP_DIRS = AppDirs("nucypher", "NuCypher")
PROJECT_ROOT = abspath(dirname(nucypher.__file__))

DEFAULT_CONFIG_ROOT = APP_DIRS.user_data_dir
DEFAULT_INI_FILEPATH = os.path.join(DEFAULT_CONFIG_ROOT, 'nucypher.ini')
DEFAULT_KEYRING_ROOT = os.path.join(DEFAULT_CONFIG_ROOT, 'keyring')

DEFAULT_REST_PORT = 5876
DEFAULT_DHT_PORT = DEFAULT_REST_PORT + 100
DEFAULT_DB_NAME = "ursula.{port}.db".format(port=DEFAULT_REST_PORT)

DEFAULT_SEED_NODE_DIR = os.path.join(DEFAULT_CONFIG_ROOT, 'seed_nodes')
DEFAULT_KNOWN_NODE_DIR = os.path.join(DEFAULT_CONFIG_ROOT, 'known_nodes')

DEFAULT_SIMULATION_PORT = 5555
DEFAULT_SIMULATION_REGISTRY_FILEPATH = os.path.join(DEFAULT_CONFIG_ROOT, 'simulation_registry.json')
