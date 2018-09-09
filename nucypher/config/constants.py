"""Nucypher configuration defaults"""


import os
from os.path import dirname, abspath

from appdirs import AppDirs

import nucypher

BASE_DIR = abspath(dirname(dirname(nucypher.__file__)))

APP_DIRS = AppDirs("nucypher", "NuCypher")
PROJECT_ROOT = abspath(dirname(nucypher.__file__))

DEFAULT_CONFIG_ROOT = APP_DIRS.user_data_dir
TEMPLATE_INI_FILEPATH = os.path.join(BASE_DIR, 'cli', '.nucypher.ini')
DEFAULT_INI_FILEPATH = os.path.join(DEFAULT_CONFIG_ROOT, 'nucypher.ini')
DEFAULT_KEYRING_ROOT = os.path.join(DEFAULT_CONFIG_ROOT, 'keyring')
DEFAULT_TLS_CERTIFICATE_FILEPATH = os.path.join(DEFAULT_CONFIG_ROOT, 'ursula.pem')

DEFAULT_REST_PORT = 9151
DEFAULT_DB_NAME = "ursula.{port}.db".format(port=DEFAULT_REST_PORT)

DEFAULT_SEED_NODE_DIR = os.path.join(DEFAULT_CONFIG_ROOT, 'seed_nodes')
DEFAULT_SEED_CERTIFICATES_DIR = os.path.join(DEFAULT_SEED_NODE_DIR, 'certificates')
DEFAULT_SEED_METADATA_DIR = os.path.join(DEFAULT_SEED_NODE_DIR, 'metadata')

DEFAULT_KNOWN_NODE_DIR = os.path.join(DEFAULT_CONFIG_ROOT, 'known_nodes')
DEFAULT_KNOWN_CERTIFICATES_DIR = os.path.join(DEFAULT_KNOWN_NODE_DIR, 'certificates')
DEFAULT_KNOWN_METADATA_DIR = os.path.join(DEFAULT_KNOWN_NODE_DIR, 'metadata')

DEFAULT_SIMULATION_PORT = 8151
DEFAULT_SIMULATION_REGISTRY_FILEPATH = os.path.join(DEFAULT_CONFIG_ROOT, 'simulation_registry.json')
