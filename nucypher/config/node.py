import contextlib
import os
from abc import abstractmethod
from tempfile import TemporaryDirectory
from typing import Iterable

from constant_sorrow import constants
from itertools import islice

from nucypher.config.constants import DEFAULT_CONFIG_ROOT, DEFAULT_CONFIG_FILE_LOCATION, TEMPLATE_CONFIG_FILE_LOCATION


class NodeConfiguration:

    class ConfigurationError(RuntimeError):
        pass

    def __init__(self,

                 temp: bool = True,
                 auto_initialize: bool = False,
                 config_root: str = None,
                 config_file_location: str = DEFAULT_CONFIG_FILE_LOCATION,
                 keyring_dir: str = None,

                 checksum_address: str = None,
                 is_me: bool = True,
                 federated_only: bool = False,
                 network_middleware=None,

                 # Informant
                 known_metadata_dir: str = None,
                 start_learning_on_same_thread: bool = True,
                 abort_on_learning_error: bool = False,
                 always_be_learning: bool = True,
                 known_nodes: Iterable = None,
                 save_metadata: bool = True

                 ) -> None:

        self.__temp_dir = constants.NO_TEMPORARY_CONFIGURATION
        if temp and not config_root:
            self.__temp_dir = constants.UNINITIALIZED_TEMPORARY_CONFIGURATION
            config_root = constants.UNINITIALIZED_TEMPORARY_CONFIGURATION
        elif not config_root:
            config_root = DEFAULT_CONFIG_ROOT

        self.temp = temp
        self.config_root = config_root
        self.config_file_location = config_file_location

        self.keyring_dir = keyring_dir or constants.UNINITIALIZED_CONFIGURATION
        self.known_nodes_dir = constants.UNINITIALIZED_CONFIGURATION
        self.known_certificates_dir = known_metadata_dir or constants.UNINITIALIZED_CONFIGURATION
        self.known_metadata_dir = known_metadata_dir or constants.UNINITIALIZED_CONFIGURATION

        if auto_initialize:
            self.initialize_configuration()

        self.checksum_address = checksum_address
        self.is_me = is_me
        self.federated_only = federated_only
        self.known_nodes = known_nodes
        self.network_middleare = network_middleware
        self.start_learning_on_same_thread = start_learning_on_same_thread
        self.abort_on_learning_error = abort_on_learning_error
        self.always_be_learning = always_be_learning
        self.save_metadata = save_metadata

    def _write_default_configuration_file(self, filepath: str = DEFAULT_CONFIG_FILE_LOCATION):
        with contextlib.ExitStack() as stack:
            template_file = stack.enter_context(open(TEMPLATE_CONFIG_FILE_LOCATION, 'r'))
            new_file = stack.enter_context(open(filepath, 'w+'))
            if new_file.read() != '':
                raise self.ConfigurationError("{} is not a blank file.  Do you have an existing configuration?")
            for line in islice(template_file, 12, None):
                new_file.writelines(line.lstrip(';'))  # TODO Copy Default Sections, Perhaps interactively

    def check_config_tree(self, configuration_dir: str = None) -> bool:
        path = configuration_dir if configuration_dir else self.config_root
        if not os.path.exists(path):
            raise self.ConfigurationError(
                'No Nucypher configuration directory found at {}.'.format(configuration_dir))
        return True

    def generate_runtime_filepaths(self) -> None:
        """Dynamically generate paths based on configuration root directory"""
        self.keyring_dir = os.path.join(self.config_root, 'keyring')
        self.known_nodes_dir = os.path.join(self.config_root, 'known_nodes')
        self.known_certificates_dir = os.path.join(self.config_root, 'certificates')
        self.known_metadata_dir = os.path.join(self.config_root, 'metadata')

    @property
    def payload(self):
        """Exported configuration values for initializing Ursula"""
        base_payload = dict(
                            # Identity
                            is_me=self.is_me,
                            federated_only=self.federated_only,
                            checksum_address=self.checksum_address,
                            # keyring_dir=self.keyring_dir,  # TODO: local private keys

                            # Behavior
                            start_learning_on_same_thread=self.start_learning_on_same_thread,
                            abort_on_learning_error=self.abort_on_learning_error,
                            always_be_learning=self.always_be_learning,
                            network_middleware=self.network_middleare,

                            # Knowledge
                            known_nodes=self.known_nodes,
                            known_certificates_dir=self.known_certificates_dir,
                            known_metadata_dir=self.known_metadata_dir
                            )
        return base_payload

    def initialize_configuration(self) -> str:
        """Create the configuration and runtime directory tree starting with thr config root directory."""

        #
        # Create Config Root
        #

        if self.temp:
            self.__temp_dir = TemporaryDirectory("nucypher-tmp-config-")
            self.config_root = self.__temp_dir.name
            self.generate_runtime_filepaths()

        else:
            self.generate_runtime_filepaths()
            try:
                os.mkdir(self.config_root, mode=0o755)
            except FileExistsError:
                message = "There are existing configuration files at {}".format(self.config_root)
                raise self.ConfigurationError(message)
            except FileNotFoundError:
                message = "Cannot write configuration files because the directory {} does not exist."
                raise self.ConfigurationError(message)

        #
        # Create Config Subdirectories
        #

        try:
            os.mkdir(self.keyring_dir, mode=0o700)               # keyring
            os.mkdir(self.known_nodes_dir, mode=0o755)           # known_nodes
            os.mkdir(self.known_certificates_dir, mode=0o755)    # known_certs
            os.mkdir(self.known_metadata_dir, mode=0o755)        # known_metadata
        except FileExistsError:
            raise  # TODO

        self.check_config_tree(configuration_dir=self.config_root)
        return self.config_root

    @classmethod
    @abstractmethod
    def from_configuration_file(cls, filepath: str):
        raise NotImplementedError

    @classmethod
    @abstractmethod
    def from_configuration_directory(cls, filepath: str):
        raise NotImplementedError
