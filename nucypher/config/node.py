import contextlib
import os
from abc import abstractmethod
from tempfile import TemporaryDirectory

from itertools import islice

from nucypher.config.constants import DEFAULT_CONFIG_ROOT, DEFAULT_CONFIG_FILE_LOCATION, TEMPLATE_CONFIG_FILE_LOCATION


class NodeConfiguration:

    DEFAULT_OPERATING_MODE = 'federated'

    class NucypherConfigurationError(RuntimeError):
        pass

    def __init__(self,
                 config_root: str = DEFAULT_CONFIG_ROOT,
                 config_file_location: str = DEFAULT_CONFIG_FILE_LOCATION,
                 operating_mode: str = DEFAULT_OPERATING_MODE,
                 temp: bool = True
                 ) -> None:

        #
        # Common
        #

        if temp is True:
            self.temp = True
            self.temp_dir = TemporaryDirectory()
            self.config_root = self.temp_dir.name
        else:
            self.config_root = config_root

        self.operating_mode = 'federated'
        self.keyring_root = os.path.join(config_root, 'keyring')
        self.known_node_dir = os.path.join(config_root, 'known_nodes')
        self.known_certificates_dir = os.path.join(config_root, 'certificates')
        self.known_metadata_dir = os.path.join(config_root, 'metadata')

        self.config_file_location = config_file_location
        self.operating_mode = operating_mode

    def _write_default_configuration_file(self, filepath: str = DEFAULT_CONFIG_FILE_LOCATION):
        with contextlib.ExitStack() as stack:
            template_file = stack.enter_context(open(TEMPLATE_CONFIG_FILE_LOCATION, 'r'))
            new_file = stack.enter_context(open(filepath, 'w+'))
            if new_file.read() != '':
                raise self.NucypherConfigurationError("{} is not a blank file.  Do you have an existing configuration?")
            for line in islice(template_file, 12, None):
                new_file.writelines(line.lstrip(';'))  # TODO Copy Default Sections, Perhaps interactively

    def _check_config_tree(self, configuration_dir: str = None) -> bool:
        path = configuration_dir if configuration_dir else DEFAULT_CONFIG_ROOT
        if not os.path.exists(path):
            raise self.NucypherConfigurationError(
                'No Nucypher configuration directory found at {}.'.format(configuration_dir))
        return True

    def initialize_configuration(self) -> str:
        """
        Create the configuration directory tree.
        If the directory already exists, FileExistsError is raised.
        """

        #
        # Create Config Root
        #

        if self.temp is False:
            if os.path.isdir(self.config_root):
                message = "There are existing nucypher configuration files at {}".format(self.config_root)
                raise self.NucypherConfigurationError(message)

            try:
                os.mkdir(self.config_root, mode=0o755)
            except FileExistsError:
                raise
            except FileNotFoundError:
                raise

        #
        # Create Config Subdirectories
        #

        os.mkdir(self.keyring_dir, mode=0o700)               # keyring
        os.mkdir(self.known_node_dir, mode=0o755)            # known_nodes
        os.mkdir(self.known_certificates_dir, mode=0o755)    # known_certs
        os.mkdir(self.known_metadata_dir, mode=0o755)        # known_metadata

        # Write a blank config file at the default path
        self._write_default_configuration_file()
        self._check_config_tree(configuration_dir=self.config_root)

        return self.config_root

    @classmethod
    @abstractmethod
    def from_config_file(cls, filepath: str):
        raise NotImplementedError
