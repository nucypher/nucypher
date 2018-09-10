import contextlib
import os
from abc import abstractmethod
from os.path import abspath, dirname

from appdirs import AppDirs
from itertools import islice

import nucypher

APP_DIRS = AppDirs("nucypher", "NuCypher")
DEFAULT_CONFIG_ROOT = APP_DIRS.user_data_dir

BASE_DIR = abspath(dirname(dirname(nucypher.__file__)))
PROJECT_ROOT = abspath(dirname(nucypher.__file__))


class NodeConfiguration:

    TEMPLATE_INI_FILEPATH = os.path.join(BASE_DIR, 'cli', '.nucypher.ini')
    DEFAULT_INI_FILEPATH = os.path.join(DEFAULT_CONFIG_ROOT, 'nucypher.ini')

    DEFAULT_KEYRING_ROOT = os.path.join(DEFAULT_CONFIG_ROOT, 'keyring')

    DEFAULT_KNOWN_NODE_DIR = os.path.join(DEFAULT_CONFIG_ROOT, 'known_nodes')
    DEFAULT_KNOWN_CERTIFICATES_DIR = os.path.join(DEFAULT_KNOWN_NODE_DIR, 'certificates')
    DEFAULT_KNOWN_METADATA_DIR = os.path.join(DEFAULT_KNOWN_NODE_DIR, 'metadata')

    DEFAULT_OPERATING_MODE = 'federated'

    class NucypherConfigurationError(RuntimeError):
        pass

    def __init__(self,
                 config_root: str = DEFAULT_CONFIG_ROOT,
                 ini_filepath: str = DEFAULT_INI_FILEPATH,
                 keyring_dir: str = DEFAULT_KEYRING_ROOT,
                 known_certificates_dir: str = DEFAULT_KNOWN_CERTIFICATES_DIR,
                 known_metedata_dir: str = DEFAULT_KNOWN_METADATA_DIR,
                 known_node_dir: str = DEFAULT_KNOWN_NODE_DIR,
                 operating_mode: str = DEFAULT_OPERATING_MODE,
                 ) -> None:

        #
        # Common
        #
        self.config_root = config_root
        self.ini_filepath = ini_filepath
        self.keyring_dir = keyring_dir
        self.known_node_dir = known_node_dir
        self.known_certificates_dir = known_certificates_dir
        self.known_metadata_dir = known_metedata_dir
        self.operating_mode = operating_mode

    def _write_default_ini_config(self, filepath: str = DEFAULT_INI_FILEPATH):
        with contextlib.ExitStack() as stack:
            template_file = stack.enter_context(open(self.TEMPLATE_INI_FILEPATH, 'r'))
            new_file = stack.enter_context(open(filepath, 'w+'))
            if new_file.read() != '':
                raise self.NucypherConfigurationError("{} is not a blank file.  Do you have an existing configuration?")
            for line in islice(template_file, 12, None):
                new_file.writelines(line.lstrip(';'))  # TODO Copy Default Sections, Perhaps interactively

    def check_config_tree(self, configuration_dir: str = None) -> bool:
        path = configuration_dir if configuration_dir else DEFAULT_CONFIG_ROOT
        if not os.path.exists(path):
            raise self.NucypherConfigurationError(
                'No Nucypher configuration directory found at {}.'.format(configuration_dir))
        return True

    def initialize_configuration(self,
                                 config_root: str = DEFAULT_CONFIG_ROOT,
                                 temp=True) -> str:
        """
        Create the configuration directory tree.
        If the directory already exists, FileExistsError is raised.
        """

        if os.path.isdir(config_root):
            message = "There are existing nucypher configuration files at {}".format(config_root)
            raise self.NucypherConfigurationError(message)

        #
        # Make configuration directories
        #

        try:
            os.mkdir(config_root, mode=0o755)       # config root    # TODO: try/except
        except FileExistsError:
            raise
        except FileNotFoundError:
            raise

        os.mkdir(self.keyring_dir, mode=0o700)  # keyring

        os.mkdir(self.known_node_dir, mode=0o755)            # known_nodes
        os.mkdir(self.known_certificates_dir, mode=0o755)    # known_certs
        os.mkdir(self.known_metadata_dir, mode=0o755)        # known_metadata

        # Make a blank ini config file at the default path
        self._write_default_ini_config()

        return config_root

    @classmethod
    @abstractmethod
    def from_config_file(cls, filepath: str):
        raise NotImplementedError
