import contextlib
import os
from abc import abstractmethod
from tempfile import TemporaryDirectory
from typing import Iterable

from itertools import islice

from nucypher.config.constants import DEFAULT_CONFIG_ROOT, DEFAULT_CONFIG_FILE_LOCATION, TEMPLATE_CONFIG_FILE_LOCATION


class NodeConfiguration:

    class ConfigurationError(RuntimeError):
        pass

    def __init__(self,

                 temp: bool = True,
                 config_root: str = None,
                 config_file_location: str = DEFAULT_CONFIG_FILE_LOCATION,

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

        self.temp = temp
        if self.temp and not config_root:
            self.temp_dir = TemporaryDirectory(prefix='nucypher-tmp-config-')
            config_root = self.temp_dir.name
        elif not config_root:
            config_root = DEFAULT_CONFIG_ROOT

        self.config_root = config_root
        self.config_file_location = config_file_location

        # Dynamically generate paths baed on configuration root directory
        self.keyring_dir = os.path.join(self.config_root, 'keyring')
        self.known_nodes_dir = os.path.join(self.config_root, 'known_nodes')
        self.known_certificates_dir = os.path.join(self.config_root, 'certificates')

        if known_metadata_dir is None:
            known_metadata_dir = os.path.join(self.config_root, 'metadata')
        self.known_metadata_dir = known_metadata_dir

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

    def _check_config_tree(self, configuration_dir: str = None) -> bool:
        path = configuration_dir if configuration_dir else DEFAULT_CONFIG_ROOT
        if not os.path.exists(path):
            raise self.ConfigurationError(
                'No Nucypher configuration directory found at {}.'.format(configuration_dir))
        return True

    @property
    def payload(self):
        base_payload = dict(is_me=self.is_me,
                            federated_only=self.federated_only,
                            checksum_address=self.checksum_address,
                            network_middleware=self.network_middleare,
                            start_learning_on_same_thread=self.start_learning_on_same_thread,
                            abort_on_learning_error=self.abort_on_learning_error,
                            always_be_learning=self.always_be_learning,
                            known_nodes=self.known_nodes,
                            known_certificates_dir=self.known_certificates_dir,
                            known_metadata_dir=self.known_metadata_dir

                            # TODO
                            # config_file_location=self.config_file_location,
                            # config_root=self.config_root,
                            # keyring_dir=self.keyring_dir,
                            )

        return base_payload

    def initialize_configuration(self) -> str:
        """
        Create the configuration directory tree.
        """

        #
        # Create Config Root
        #

        if not self.temp:
            if os.path.isdir(self.config_root):
                message = "There are existing configuration files at {}".format(self.config_root)
                raise self.ConfigurationError(message)

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
        os.mkdir(self.known_nodes_dir, mode=0o755)           # known_nodes
        os.mkdir(self.known_certificates_dir, mode=0o755)    # known_certs
        os.mkdir(self.known_metadata_dir, mode=0o755)        # known_metadata

        self._check_config_tree(configuration_dir=self.config_root)

        return self.config_root

    @classmethod
    @abstractmethod
    def from_config_file(cls, filepath: str):
        raise NotImplementedError
