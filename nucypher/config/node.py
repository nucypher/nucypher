import contextlib
import json
import os
import shutil
from glob import glob
from os.path import abspath
from tempfile import TemporaryDirectory

from constant_sorrow import constants
from itertools import islice

from nucypher.characters.base import Character
from nucypher.config.constants import DEFAULT_CONFIG_ROOT, DEFAULT_CONFIG_FILE_LOCATION, TEMPLATE_CONFIG_FILE_LOCATION, \
    BASE_DIR
from nucypher.network.middleware import RestMiddleware


class NodeConfiguration:

    _Character = NotImplemented
    _parser = NotImplemented

    DEFAULT_OPERATING_MODE = 'decentralized'

    __TEMP_CONFIGURATION_DIR_PREFIX = "nucypher-tmp-"
    __DEFAULT_NETWORK_MIDDLEWARE_CLASS = RestMiddleware

    __REGISTRY_NAME = 'contract_registry.json'
    __REGISTRY_SOURCE = os.path.join(BASE_DIR, __REGISTRY_NAME)  # TODO

    class ConfigurationError(RuntimeError):
        pass

    class InvalidConfiguration(RuntimeError):
        pass

    def __init__(self,

                 temp: bool = False,
                 auto_initialize: bool = False,
                 config_root: str = DEFAULT_CONFIG_ROOT,

                 config_file_location: str = DEFAULT_CONFIG_FILE_LOCATION,
                 keyring_dir: str = None,

                 checksum_address: str = None,
                 is_me: bool = True,
                 federated_only: bool = None,
                 network_middleware: RestMiddleware = None,

                 registry_source: str = __REGISTRY_SOURCE,
                 registry_filepath: str = None,
                 no_seed_registry: bool = False,

                 # Learner
                 learn_on_same_thread: bool = False,
                 abort_on_learning_error: bool = False,
                 start_learning_now: bool = True,

                 # Metadata
                 known_nodes: set = None,
                 known_metadata_dir: str = None,
                 load_metadata: bool = False,
                 save_metadata: bool = False

                 ) -> None:

        #
        # Configuration Filepaths
        #

        self.keyring_dir = keyring_dir or constants.UNINITIALIZED_CONFIGURATION
        self.known_nodes_dir = constants.UNINITIALIZED_CONFIGURATION
        self.known_certificates_dir = known_metadata_dir or constants.UNINITIALIZED_CONFIGURATION
        self.known_metadata_dir = known_metadata_dir or constants.UNINITIALIZED_CONFIGURATION

        self.__registry_source = registry_source
        self.registry_filepath = registry_filepath or constants.UNINITIALIZED_CONFIGURATION

        self.config_root = constants.UNINITIALIZED_CONFIGURATION
        self.__temp = temp

        if self.__temp:
            self.__temp_dir = constants.UNINITIALIZED_CONFIGURATION
        else:
            self.config_root = config_root
            self.__temp_dir = constants.LIVE_CONFIGURATION
            self.__cache_runtime_filepaths()

        self.config_file_location = config_file_location

        #
        # Identity
        #

        self.is_me = is_me
        self.checksum_address = checksum_address
        if not federated_only:  # TODO: get_config function?
            federated_only = True if self.DEFAULT_OPERATING_MODE is 'federated' else False
        self.federated_only = federated_only

        #
        # Network & Learning
        #

        if is_me:
            network_middleware = network_middleware or self.__DEFAULT_NETWORK_MIDDLEWARE_CLASS()
        self.network_middleware = network_middleware

        self.known_nodes = known_nodes or set()
        self.learn_on_same_thread = learn_on_same_thread
        self.abort_on_learning_error = abort_on_learning_error
        self.start_learning_now = start_learning_now
        self.save_metadata = save_metadata

        #
        # Auto-Initialization
        #

        if auto_initialize:
            self.write_defaults(no_registry=no_seed_registry)             # <<< Write runtime files and dirs
        if load_metadata:
            self.load_known_nodes(known_metadata_dir=known_metadata_dir)

    @property
    def temp(self):
        return self.__temp

    @classmethod
    def from_configuration_file(cls, filepath=None) -> 'NodeConfiguration':
        filepath = filepath if filepath is None else DEFAULT_CONFIG_FILE_LOCATION
        payload = cls._parser(filepath=filepath)
        return cls(**payload)

    @property
    def payload(self):
        """Exported configuration values for initializing Ursula"""
        base_payload = dict(
                            # Identity
                            is_me=self.is_me,
                            federated_only=self.federated_only,  # TODO: 466
                            checksum_address=self.checksum_address,
                            # keyring_dir=self.keyring_dir,  # TODO: local private keys

                            # Behavior
                            learn_on_same_thread=self.learn_on_same_thread,
                            abort_on_learning_error=self.abort_on_learning_error,
                            start_learning_now=self.start_learning_now,
                            network_middleware=self.network_middleware,

                            # Knowledge
                            known_nodes=self.known_nodes,
                            known_certificates_dir=self.known_certificates_dir,
                            known_metadata_dir=self.known_metadata_dir,
                            save_metadata=self.save_metadata
                            )
        return base_payload

    @staticmethod
    def generate_runtime_filepaths(config_root: str) -> dict:
        """Dynamically generate paths based on configuration root directory"""
        known_nodes_dir = os.path.join(config_root, 'known_nodes')
        filepaths = dict(config_root=config_root,
                         keyring_dir=os.path.join(config_root, 'keyring'),
                         known_nodes_dir=known_nodes_dir,
                         known_certificates_dir=os.path.join(known_nodes_dir, 'certificates'),
                         known_metadata_dir=os.path.join(known_nodes_dir, 'metadata'),
                         registry_filepath=os.path.join(config_root, NodeConfiguration.__REGISTRY_NAME))
        return filepaths

    @staticmethod
    def check_config_tree_exists(config_root: str) -> bool:
        # Top-level
        if not os.path.exists(config_root):
            raise NodeConfiguration.ConfigurationError('No configuration directory found at {}.'.format(config_root))

        # Sub-paths
        filepaths = NodeConfiguration.generate_runtime_filepaths(config_root=config_root)
        for field, path in filepaths.items():
            if not os.path.exists(path):
                message = 'Missing configuration directory {}.'
                raise NodeConfiguration.InvalidConfiguration(message.format(path))

        return True

    def __cache_runtime_filepaths(self) -> None:
        """Generate runtime filepaths and cache them on the config object"""
        filepaths = self.generate_runtime_filepaths(config_root=self.config_root)
        for field, filepath in filepaths.items():
            if getattr(self, field) is constants.UNINITIALIZED_CONFIGURATION:
                setattr(self, field, filepath)

    def write_defaults(self) -> str:
        """Writes the configuration and runtime directory tree starting with the config root directory."""

        #
        # Create Config Root
        #
        if self.__temp:
            self.__temp_dir = TemporaryDirectory(prefix=self.__TEMP_CONFIGURATION_DIR_PREFIX)
            self.config_root = self.__temp_dir.name
        else:
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
        self.__cache_runtime_filepaths()
        try:

            # Directories
            os.mkdir(self.keyring_dir, mode=0o700)               # keyring
            os.mkdir(self.known_nodes_dir, mode=0o755)           # known_nodes
            os.mkdir(self.known_certificates_dir, mode=0o755)    # known_certs
            os.mkdir(self.known_metadata_dir, mode=0o755)        # known_metadata

            # Files
            self.import_registry(output_filepath=self.registry_filepath,
                                 source=self.__registry_source)

        except FileExistsError:
            existing_paths = [os.path.join(self.config_root, f) for f in os.listdir(self.config_root)]
            message = "There are pre-existing nucypher installation files at {}: {}".format(self.config_root, existing_paths)
            raise NodeConfiguration.ConfigurationError(message)

        # self.check_config_tree_exists(config_root=self.config_root)
        return self.config_root

    def load_known_nodes(self, known_metadata_dir=None) -> None:

        if known_metadata_dir is None:
            known_metadata_dir = self.known_metadata_dir

        glob_pattern = os.path.join(known_metadata_dir, '*.node')
        metadata_paths = sorted(glob(glob_pattern), key=os.path.getctime)

        for metadata_path in metadata_paths:
            from nucypher.characters.lawful import Ursula
            node = Ursula.from_metadata_file(filepath=abspath(metadata_path), federated_only=self.federated_only)  # TODO: 466
            self.known_nodes.add(node)

    def import_registry(self,
                        output_filepath: str = None,
                        source: str = None,
                        force: bool = False,
                        blank=False) -> str:

        # if force and os.path.isfile(output_filepath):
        #     raise self.ConfigurationError('There is an existing file at the registry output_filepath {}'.format(output_filepath))
        #
        # output_filepath = output_filepath or self.registry_filepath
        # source = source or self.__REGISTRY_SOURCE
        #
        # # TODO: Validate registry
        #
        # if not blank:
        #     shutil.copyfile(src=source, dst=output_filepath)
        # else:
        #     open(output_filepath, '').close()  # blank

        return output_filepath

    def write_default_configuration_file(self, filepath: str = DEFAULT_CONFIG_FILE_LOCATION):
        with contextlib.ExitStack() as stack:
            template_file = stack.enter_context(open(TEMPLATE_CONFIG_FILE_LOCATION, 'r'))
            new_file = stack.enter_context(open(filepath, 'w+'))
            if new_file.read() != '':
                message = "{} is not a blank file.  Do you have an existing configuration file?"
                raise self.ConfigurationError(message)

            for line in islice(template_file, 12, None):  # chop the warning header
                new_file.writelines(line.lstrip(';'))  # TODO Copy Default Sections, Perhaps interactively

    def cleanup(self) -> None:
        if self.__temp:
            self.__temp_dir.cleanup()

    def produce(self, **overrides) -> Character:
        """Initialize a new character instance and return it"""
        merged_parameters = {**self.payload, **overrides}
        return self._Character(**merged_parameters)
