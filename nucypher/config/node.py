import binascii
import json
import os
from json import JSONDecodeError
from logging import getLogger
from tempfile import TemporaryDirectory
from typing import List

from constant_sorrow import constants

from nucypher.config.constants import DEFAULT_CONFIG_ROOT, BASE_DIR
from nucypher.config.keyring import NucypherKeyring
from nucypher.config.storages import NodeStorage, InMemoryNodeStorage, LocalFileBasedNodeStorage
from nucypher.crypto.powers import CryptoPowerUp
from nucypher.network.middleware import RestMiddleware


class NodeConfiguration:
    _name = 'node'
    _Character = NotImplemented

    DEFAULT_CONFIG_FILE_LOCATION = os.path.join(DEFAULT_CONFIG_ROOT, '{}.config'.format(_name))
    DEFAULT_OPERATING_MODE = 'decentralized'
    NODE_SERIALIZER = binascii.hexlify
    NODE_DESERIALIZER = binascii.unhexlify

    __CONFIG_FILE_EXT = '.config'
    __CONFIG_FILE_DESERIALIZER = json.loads
    __TEMP_CONFIGURATION_DIR_PREFIX = "nucypher-tmp-"
    __DEFAULT_NETWORK_MIDDLEWARE_CLASS = RestMiddleware
    __DEFAULT_NODE_STORAGE = LocalFileBasedNodeStorage

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
                 node_storage: NodeStorage = None,
                 load_metadata: bool = True,
                 save_metadata: bool = True

                 ) -> None:

        self.log = getLogger(self.__class__.__name__)

        # Known Nodes
        self.known_nodes_dir = constants.UNINITIALIZED_CONFIGURATION
        self.known_certificates_dir = known_certificates_dir or constants.UNINITIALIZED_CONFIGURATION

        # Keyring
        self.keyring = constants.UNINITIALIZED_CONFIGURATION
        self.keyring_dir = keyring_dir or constants.UNINITIALIZED_CONFIGURATION

        # Contract Registry
        self.__registry_source = registry_source
        self.registry_filepath = registry_filepath or constants.UNINITIALIZED_CONFIGURATION

        # Configuration Root Directory
        self.config_root = constants.UNINITIALIZED_CONFIGURATION
        self.__temp = temp
        if self.__temp:
            self.__temp_dir = constants.UNINITIALIZED_CONFIGURATION
            self.node_storage = InMemoryNodeStorage(federated_only=federated_only,
                                                    character_class=self.__class__)
        else:
            self.config_root = config_root
            self.__temp_dir = constants.LIVE_CONFIGURATION
            from nucypher.characters.lawful import Ursula  # TODO : Needs cleanup
            self.node_storage = node_storage or self.__DEFAULT_NODE_STORAGE(federated_only=federated_only,
                                                                            character_class=Ursula)
            self.__cache_runtime_filepaths()
        self.config_file_location = config_file_location

        #
        # Identity
        #
        self.federated_only = federated_only
        self.checksum_address = checksum_address
        self.is_me = is_me
        if self.is_me:
            #
            # Self
            #
            if checksum_address and not self.__temp:
                self.read_keyring()
            self.network_middleware = network_middleware or self.__DEFAULT_NETWORK_MIDDLEWARE_CLASS()
        else:
            #
            # Stranger
            #
            self.known_nodes_dir = constants.STRANGER_CONFIGURATION
            self.known_certificates_dir = constants.STRANGER_CONFIGURATION
            self.node_storage = constants.STRANGER_CONFIGURATION
            self.keyring_dir = constants.STRANGER_CONFIGURATION
            self.keyring = constants.STRANGER_CONFIGURATION
            self.network_middleware = constants.STRANGER_CONFIGURATION
            if network_middleware:
                raise self.ConfigurationError("Cannot configure a stranger to use network middleware")

        #
        # Learner
        #
        self.known_nodes = known_nodes or set()
        self.learn_on_same_thread = learn_on_same_thread
        self.abort_on_learning_error = abort_on_learning_error
        self.start_learning_now = start_learning_now
        self.save_metadata = save_metadata
        self.load_metadata = load_metadata

        #
        # Auto-Initialization
        #
        if auto_initialize:
            self.initialize(no_registry=not import_seed_registry or federated_only,
                            wallet=auto_generate_keys and not federated_only,
                            encrypting=auto_generate_keys,
                            passphrase=passphrase)

    def __call__(self, *args, **kwargs):
        return self.produce(*args, **kwargs)

    def cleanup(self) -> None:
        if self.__temp:
            self.__temp_dir.cleanup()

    @property
    def temp(self):
        return self.__temp

    def produce(self, passphrase: str = None, **overrides):
        """Initialize a new character instance and return it"""
        if not self.temp:
            self.read_keyring()
            self.keyring.unlock(passphrase=passphrase)
        merged_parameters = {**self.static_payload, **self.dynamic_payload, **overrides}
        return self._Character(**merged_parameters)

    @classmethod
    def from_configuration_file(cls, filepath, **overrides) -> 'NodeConfiguration':
        """Initialize a NodeConfiguration from a JSON file."""
        from nucypher.config.storages import NodeStorage  # TODO: move
        NODE_STORAGES = {storage_class._name: storage_class for storage_class in NodeStorage.__subclasses__()}

        with open(filepath, 'r') as file:
            payload = cls.__CONFIG_FILE_DESERIALIZER(file.read())

        # Make NodeStorage
        storage_payload = payload['node_storage']
        storage_type = storage_payload[NodeStorage._TYPE_LABEL]
        storage_class = NODE_STORAGES[storage_type]
        node_storage = storage_class.from_payload(payload=storage_payload,
                                                  character_class=cls._Character,
                                                  federated_only=payload['federated_only'],
                                                  serializer=cls.NODE_SERIALIZER,
                                                  deserializer=cls.NODE_DESERIALIZER)

        payload.update(dict(node_storage=node_storage))
        return cls(**{**payload, **overrides})

    def to_configuration_file(self, filepath: str = None) -> str:
        """Write the static_payload to a JSON file."""
        if filepath is None:
            filename = '{}{}'.format(self._name.lower(), self.__CONFIG_FILE_EXT)
            filepath = os.path.join(self.config_root, filename)

        payload = self.static_payload
        # Save node connection data
        payload.update(dict(node_storage=self.node_storage.payload()))

        with open(filepath, 'w') as config_file:
            config_file.write(json.dumps(payload, indent=4))
        return filepath

    def validate(self, config_root: str, no_registry=False) -> bool:
        # Top-level
        if not os.path.exists(config_root):
            raise self.ConfigurationError('No configuration directory found at {}.'.format(config_root))

        # Sub-paths
        filepaths = self.runtime_filepaths
        if no_registry:
            del filepaths['registry_filepath']

        for field, path in filepaths.items():
            if not os.path.exists(path):
                message = 'Missing configuration directory {}.'
                raise NodeConfiguration.InvalidConfiguration(message.format(path))
        return True

    @property
    def static_payload(self) -> dict:
        """Exported static configuration values for initializing Ursula"""
        payload = dict(
            # Identity
            is_me=self.is_me,
            federated_only=self.federated_only,  # TODO: 466
            checksum_address=self.checksum_address,
            keyring_dir=self.keyring_dir,
            known_certificates_dir=self.known_certificates_dir,

            # Behavior
            learn_on_same_thread=self.learn_on_same_thread,
            abort_on_learning_error=self.abort_on_learning_error,
            start_learning_now=self.start_learning_now,
            save_metadata=self.save_metadata
        )
        return payload

    @property
    def dynamic_payload(self, **overrides) -> dict:
        """Exported dynamic configuration values for initializing Ursula"""
        if self.load_metadata:
            self.known_nodes.update(self.node_storage.all(federated_only=self.federated_only))
        payload = dict(network_middleware=self.network_middleware or self.__DEFAULT_NETWORK_MIDDLEWARE_CLASS(),
                       known_nodes=self.known_nodes,
                       node_storage=self.node_storage,
                       crypto_power_ups=self.derive_node_power_ups() or None)
        if overrides:
            self.log.debug("Overrides supplied to dynamic payload for {}".format(self.__class__.__name__))
            payload.update(overrides)
        return payload

    @property
    def runtime_filepaths(self):
        filepaths = dict(config_root=self.config_root,
                         keyring_dir=self.keyring_dir,
                         known_certificates_dir=self.known_certificates_dir,
                         registry_filepath=self.registry_filepath)
        return filepaths

    @staticmethod
    def generate_runtime_filepaths(config_root: str) -> dict:
        """Dynamically generate paths based on configuration root directory"""
        known_nodes_dir = os.path.join(config_root, 'known_nodes')
        filepaths = dict(config_root=config_root,
                         keyring_dir=os.path.join(config_root, 'keyring'),
                         known_nodes_dir=known_nodes_dir,
                         known_certificates_dir=os.path.join(known_nodes_dir, 'certificates'),
                         registry_filepath=os.path.join(config_root, NodeConfiguration.__REGISTRY_NAME))
        return filepaths

    def __cache_runtime_filepaths(self) -> None:
        """Generate runtime filepaths and cache them on the config object"""
        filepaths = self.generate_runtime_filepaths(config_root=self.config_root)
        for field, filepath in filepaths.items():
            if getattr(self, field) is constants.UNINITIALIZED_CONFIGURATION:
                setattr(self, field, filepath)

    def derive_node_power_ups(self) -> List[CryptoPowerUp]:
        power_ups = list()
        if self.is_me and not self.temp:
            for power_class in self._Character._default_crypto_powerups:
                power_up = self.keyring.derive_crypto_power(power_class)
                power_ups.append(power_up)
        return power_ups

    def initialize(self,
                   passphrase: str,
                   no_registry: bool = False,
                   wallet: bool = False,
                   encrypting: bool = False,
                   tls: bool = False,
                   host: str = None,
                   curve=None,
                   no_keys: bool = False
                   ) -> str:
        """Write a new configuration to the disk, and with the configured node store."""

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
            os.mkdir(self.keyring_dir, mode=0o700)  # keyring
            os.mkdir(self.known_nodes_dir, mode=0o755)  # known_nodes
            os.mkdir(self.known_certificates_dir, mode=0o755)  # known_certs
            self.node_storage.initialize()  # TODO: default know dir

            if not self.temp and not no_keys:
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
            message = "There are pre-existing nucypher installation files at {}: {}".format(self.config_root,
                                                                                            existing_paths)
            self.log.critical(message)
            raise NodeConfiguration.ConfigurationError(message)

        if not self.__temp:
            self.validate(config_root=self.config_root, no_registry=no_registry or self.federated_only)
        return self.config_root

    def read_keyring(self, *args, **kwargs):
        if self.checksum_address is None:
            raise self.ConfigurationError("No account specified to unlock keyring")
        self.keyring = NucypherKeyring(keyring_root=self.keyring_dir,
                                       account=self.checksum_address,
                                       *args, **kwargs)

    def write_keyring(self,
                      passphrase: str,
                      encrypting: bool,
                      wallet: bool,
                      tls: bool,
                      host: str,
                      tls_curve,
                      ) -> NucypherKeyring:

        self.keyring = NucypherKeyring.generate(passphrase=passphrase,
                                                encrypting=encrypting,
                                                wallet=wallet,
                                                tls=tls,
                                                host=host,
                                                curve=tls_curve,
                                                keyring_root=self.keyring_dir)

        # TODO: Operating mode switch #466
        if self.federated_only or not wallet:
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
            raise self.ConfigurationError(
                'There is an existing file at the registry output_filepath {}'.format(output_filepath))

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
            open(output_filepath, 'w').close()  # write blank

        self.log.info("Successfully wrote registry to {}".format(output_filepath))
        return output_filepath
