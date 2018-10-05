import json
import os
from glob import glob
from json import JSONDecodeError
from logging import getLogger
from os.path import abspath
from tempfile import TemporaryDirectory

from constant_sorrow import constants

from nucypher.characters.base import Character
from nucypher.config.constants import DEFAULT_CONFIG_ROOT, BASE_DIR
from nucypher.config.keyring import NucypherKeyring
from nucypher.network.middleware import RestMiddleware
from nucypher.utilities.sandbox.constants import TEST_URSULA_INSECURE_DEVELOPMENT_PASSWORD


class NodeConfiguration:
    _name = 'node'

    DEFAULT_CONFIG_FILE_LOCATION = os.path.join(DEFAULT_CONFIG_ROOT, '{}.config'.format(_name))

    _Character = NotImplemented
    __parser = json.loads

    DEFAULT_OPERATING_MODE = 'decentralized'

    __TEMP_CONFIGURATION_DIR_PREFIX = "nucypher-tmp-"
    __DEFAULT_NETWORK_MIDDLEWARE_CLASS = RestMiddleware

    __REGISTRY_NAME = 'contract_registry.json'
    REGISTRY_SOURCE = os.path.join(BASE_DIR, __REGISTRY_NAME)  # TODO: #461 Where will this be hosted?

    class ConfigurationError(RuntimeError):
        pass

    class InvalidConfiguration(ConfigurationError):
        pass

    def __init__(self,

                 temp: bool = False,
                 config_root: str = DEFAULT_CONFIG_ROOT,

                 passphrase: str = None,
                 auto_initialize: bool = False,
                 auto_generate_keys: bool = False,

                 config_file_location: str = DEFAULT_CONFIG_FILE_LOCATION,
                 keyring_dir: str = None,

                 checksum_address: str = None,
                 is_me: bool = True,
                 federated_only: bool = False,
                 network_middleware: RestMiddleware = None,

                 registry_source: str = REGISTRY_SOURCE,
                 registry_filepath: str = None,
                 import_seed_registry: bool = False,

                 # Learner
                 learn_on_same_thread: bool = False,
                 abort_on_learning_error: bool = False,
                 start_learning_now: bool = True,

                 # TLS
                 known_certificates_dir: str = None,

                 # Metadata
                 known_nodes: set = None,
                 known_metadata_dir: str = None,
                 load_metadata: bool = False,
                 save_metadata: bool = False

                 ) -> None:

        self.log = getLogger(self.__class__.__name__)

        #
        # Configuration Filepaths
        #

        self.keyring_dir = keyring_dir or constants.UNINITIALIZED_CONFIGURATION
        self.known_nodes_dir = constants.UNINITIALIZED_CONFIGURATION
        self.known_certificates_dir = known_certificates_dir or constants.UNINITIALIZED_CONFIGURATION
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
        self.federated_only = federated_only
        self.checksum_address = checksum_address
        self.is_me = is_me
        if self.is_me:
            self.keyring = NucypherKeyring(keyring_root=keyring_dir, common_name=checksum_address)
            network_middleware = network_middleware or self.__DEFAULT_NETWORK_MIDDLEWARE_CLASS()
            self.network_middleware = network_middleware
        else:
            if network_middleware:
                raise self.ConfigurationError("Cannot configure a stranger to use network middleware")
            self.known_nodes_dir = constants.STRANGER_CONFIGURATION
            self.known_certificates_dir = constants.STRANGER_CONFIGURATION
            self.known_metadata_dir = constants.STRANGER_CONFIGURATION
            self.network_middleware = constants.STRANGER_CONFIGURATION
            self.keyring_dir = constants.STRANGER_CONFIGURATION
            self.keyring = constants.STRANGER_CONFIGURATION

        #
        # Learner
        #
        self.known_nodes = known_nodes or set()
        self.learn_on_same_thread = learn_on_same_thread
        self.abort_on_learning_error = abort_on_learning_error
        self.start_learning_now = start_learning_now
        self.save_metadata = save_metadata

        #
        # Auto-Initialization
        #

        if auto_initialize:
            self.write(no_registry=not import_seed_registry or federated_only,
                       wallet=auto_generate_keys and not federated_only,
                       encrypting=auto_generate_keys,
                       passphrase=passphrase)
        if load_metadata:
            self.read_known_nodes(known_metadata_dir=known_metadata_dir)

    @property
    def temp(self):
        return self.__temp

    @classmethod
    def from_configuration_file(cls, filepath: str = None, **overrides) -> 'NodeConfiguration':
        filepath = filepath if filepath is None else cls.DEFAULT_CONFIG_FILE_LOCATION
        with open(filepath, 'r') as config_file:
            payload = cls.__parser(config_file.read())
        return cls(**{**payload, **overrides})

    def to_configuration_file(self, filepath: str = None) -> str:
        if filepath is None:
            filename = '{}.config'.format(self._name.lower())
            filepath = os.path.join(self.config_root, filename)
        with open(filepath, 'w') as config_file:
            config_file.write(json.dumps(self.static_payload, indent=4))
        return filepath

    @property
    def static_payload(self):
        """Exported static configuration values for initializing Ursula"""
        payload = dict(
                    # Identity
                    is_me=self.is_me,
                    federated_only=self.federated_only,  # TODO: 466
                    checksum_address=self.checksum_address,
                    keyring_dir=self.keyring_dir,

                    # Behavior
                    learn_on_same_thread=self.learn_on_same_thread,
                    abort_on_learning_error=self.abort_on_learning_error,
                    start_learning_now=self.start_learning_now,

                    known_certificates_dir=self.known_certificates_dir,
                    known_metadata_dir=self.known_metadata_dir,
                    save_metadata=self.save_metadata
                )
        return payload

    @property
    def dynamic_payload(self, **overrides) -> dict:
        """Exported dynamic configuration values for initializing Ursula"""
        if overrides:
            self.log.debug("Overrides supplied to dynamic payload for {}".format(self.__class__.__name__))

        if self.is_me and not self.temp:
            power_ups = tuple(self.keyring.derive_crypto_power(PowerUp)
                              for PowerUp in self._Character._default_crypto_powerups)
        else:
            power_ups = None

        payload = dict(network_middleware=self.network_middleware or self.__DEFAULT_NETWORK_MIDDLEWARE_CLASS(),
                       known_nodes=self.known_nodes,
                       crypto_power_ups=power_ups)
        return payload

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
    def validate(config_root: str, no_registry=False) -> bool:
        # Top-level
        if not os.path.exists(config_root):
            raise NodeConfiguration.ConfigurationError('No configuration directory found at {}.'.format(config_root))

        # Sub-paths
        filepaths = NodeConfiguration.generate_runtime_filepaths(config_root=config_root)
        if no_registry:
            del filepaths['registry_filepath']
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

    def write(self,
              passphrase: str,
              no_registry: bool = False,
              wallet: bool = False,
              encrypting: bool = False,
              tls: bool = False,
              host: str = None,
              curve=None
              ) -> str:

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

            if not self.temp:
                # Keyring
                self.write_keyring(passphrase=passphrase,
                                   wallet=wallet,
                                   encrypting=encrypting,
                                   tls=tls,
                                   host=host,
                                   tls_curve=curve)

            # Registry
            if not no_registry and not self.federated_only:
                self.write_registry(output_filepath=self.registry_filepath,
                                    source=self.__registry_source,
                                    blank=no_registry)

        except FileExistsError:
            existing_paths = [os.path.join(self.config_root, f) for f in os.listdir(self.config_root)]
            message = "There are pre-existing nucypher installation files at {}: {}".format(self.config_root, existing_paths)
            self.log.critical(message)
            raise NodeConfiguration.ConfigurationError(message)

        self.validate(config_root=self.config_root, no_registry=no_registry or self.federated_only)
        return self.config_root

    def read_known_nodes(self, known_metadata_dir=None) -> None:
        from nucypher.characters.lawful import Ursula

        if known_metadata_dir is None:
            known_metadata_dir = self.known_metadata_dir

        glob_pattern = os.path.join(known_metadata_dir, '*.node')
        metadata_paths = sorted(glob(glob_pattern), key=os.path.getctime)

        self.log.info("Found {} known node metadata files at {}".format(len(metadata_paths), known_metadata_dir))
        for metadata_path in metadata_paths:
            node = Ursula.from_metadata_file(filepath=abspath(metadata_path), federated_only=self.federated_only)  # TODO: 466
            self.known_nodes.add(node)

    def write_keyring(self,
                      passphrase: str,
                      encrypting: bool,
                      wallet: bool,
                      tls: bool,
                      host: str,
                      tls_curve):

        self.keyring = NucypherKeyring.generate(passphrase=passphrase,
                                                encrypting=encrypting,
                                                wallet=wallet,
                                                tls=tls,
                                                host=host,
                                                curve=tls_curve,
                                                keyring_root=self.keyring_dir,
                                                exists_ok=False)  # TODO: exists?
        if self.federated_only:
            self.checksum_address = self.keyring.federated_address
        else:
            self.checksum_address = self.keyring.checksum_address
        if tls:
            self.certificate_filepath = self.keyring.certificate_filepath
        return self.keyring

    def write_registry(self,
                       output_filepath: str = None,
                       source: str = None,
                       force: bool = False,
                       blank=False) -> str:

        if force and os.path.isfile(output_filepath):
            raise self.ConfigurationError('There is an existing file at the registry output_filepath {}'.format(output_filepath))

        output_filepath = output_filepath or self.registry_filepath
        source = source or self.REGISTRY_SOURCE

        if not blank and not self.temp:
            # Validate Registry
            with open(source, 'r') as registry_file:
                try:
                    json.loads(registry_file.read())
                except JSONDecodeError:
                    message = "The registry source {} is not valid JSON".format(source)
                    self.log.critical(message)
                    raise self.ConfigurationError(message)
                else:
                    self.log.debug("Source registry {} is valid JSON".format(source))

        else:
            self.log.warning("Writing blank registry")
            open(output_filepath, 'w').close()  # blank

        self.log.info("Successfully wrote registry to {}".format(output_filepath))
        return output_filepath

    def cleanup(self) -> None:
        if self.__temp:
            self.__temp_dir.cleanup()

    def produce(self, **overrides) -> Character:
        """Initialize a new character instance and return it"""
        if not self.temp:
            self.keyring.unlock(passphrase=TEST_URSULA_INSECURE_DEVELOPMENT_PASSWORD)  # TODO re/move this
        merged_parameters = {**self.static_payload, **self.dynamic_payload, **overrides}
        return self._Character(**merged_parameters)
