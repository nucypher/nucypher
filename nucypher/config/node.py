"""
This file is part of nucypher.

nucypher is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

nucypher is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with nucypher.  If not, see <https://www.gnu.org/licenses/>.
"""


import binascii
import json
import os
from json import JSONDecodeError
from tempfile import TemporaryDirectory
from typing import List
from web3.middleware import geth_poa_middleware

from constant_sorrow.constants import UNINITIALIZED_CONFIGURATION, STRANGER_CONFIGURATION, LIVE_CONFIGURATION
from cryptography.hazmat.primitives.asymmetric.ec import EllipticCurve
from twisted.logger import Logger

from nucypher.blockchain.eth.agents import PolicyAgent, MinerAgent, NucypherTokenAgent
from nucypher.blockchain.eth.chains import Blockchain
from nucypher.characters.lawful import Ursula
from nucypher.config.constants import DEFAULT_CONFIG_ROOT, BASE_DIR
from nucypher.config.keyring import NucypherKeyring
from nucypher.config.storages import NodeStorage, ForgetfulNodeStorage, LocalFileBasedNodeStorage
from nucypher.crypto.powers import CryptoPowerUp
from nucypher.network.middleware import RestMiddleware


class NodeConfiguration:

    _name = 'ursula'
    _character_class = Ursula

    CONFIG_FILENAME = '{}.config'.format(_name)
    DEFAULT_CONFIG_FILE_LOCATION = os.path.join(DEFAULT_CONFIG_ROOT, CONFIG_FILENAME)
    DEFAULT_OPERATING_MODE = 'decentralized'
    NODE_SERIALIZER = binascii.hexlify
    NODE_DESERIALIZER = binascii.unhexlify

    __CONFIG_FILE_EXT = '.config'
    __CONFIG_FILE_DESERIALIZER = json.loads
    __TEMP_CONFIGURATION_DIR_PREFIX = "nucypher-tmp-"
    __DEFAULT_NETWORK_MIDDLEWARE_CLASS = RestMiddleware

    __REGISTRY_NAME = 'contract_registry.json'
    REGISTRY_SOURCE = os.path.join(BASE_DIR, __REGISTRY_NAME)  # TODO: #461 Where will this be hosted?

    class ConfigurationError(RuntimeError):
        pass

    class InvalidConfiguration(ConfigurationError):
        pass

    def __init__(self,

                 dev: bool = False,
                 config_root: str = None,

                 password: str = None,
                 auto_initialize: bool = False,
                 auto_generate_keys: bool = False,

                 config_file_location: str = None,
                 keyring: NucypherKeyring = None,
                 keyring_dir: str = None,

                 checksum_address: str = None,
                 is_me: bool = True,
                 federated_only: bool = False,
                 network_middleware: RestMiddleware = None,

                 registry_source: str = None,
                 registry_filepath: str = None,
                 import_seed_registry: bool = False,

                 # Learner
                 learn_on_same_thread: bool = False,
                 abort_on_learning_error: bool = False,
                 start_learning_now: bool = True,

                 # Node Storage
                 known_nodes: set = None,
                 node_storage: NodeStorage = None,
                 load_metadata: bool = True,
                 save_metadata: bool = True,
                 ) -> None:

        # Logs
        self.log = Logger(self.__class__.__name__)

        # Keyring
        self.keyring = keyring or UNINITIALIZED_CONFIGURATION
        self.keyring_dir = keyring_dir or UNINITIALIZED_CONFIGURATION

        # Contract Registry
        self.__registry_source = registry_source or self.REGISTRY_SOURCE
        self.registry_filepath = registry_filepath or UNINITIALIZED_CONFIGURATION

        # Configuration File and Root Directory
        self.config_file_location = config_file_location or UNINITIALIZED_CONFIGURATION
        self.config_root = UNINITIALIZED_CONFIGURATION
        self.__dev = dev
        if self.__dev:
            self.__temp_dir = UNINITIALIZED_CONFIGURATION
            self.node_storage = ForgetfulNodeStorage(federated_only=federated_only, character_class=self.__class__)
        else:
            from nucypher.characters.lawful import Ursula  # TODO : Needs cleanup

            self.__temp_dir = LIVE_CONFIGURATION
            self.config_root = config_root or DEFAULT_CONFIG_ROOT
            self.__cache_runtime_filepaths()

            self.node_storage = node_storage or LocalFileBasedNodeStorage(federated_only=federated_only,
                                                                          config_root=self.config_root)


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
            if checksum_address and not self.__dev:
                self.read_keyring()
            self.network_middleware = network_middleware or self.__DEFAULT_NETWORK_MIDDLEWARE_CLASS()
        else:
            #
            # Stranger
            #
            self.node_storage = STRANGER_CONFIGURATION
            self.keyring_dir = STRANGER_CONFIGURATION
            self.keyring = STRANGER_CONFIGURATION
            self.network_middleware = STRANGER_CONFIGURATION
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
            self.initialize(no_registry=not import_seed_registry or federated_only,  # TODO: needs cleanup
                            wallet=auto_generate_keys and not federated_only,
                            encrypting=auto_generate_keys,
                            password=password)

    def __call__(self, *args, **kwargs):
        return self.produce(*args, **kwargs)

    def cleanup(self) -> None:
        if self.__dev:
            self.__temp_dir.cleanup()

    @property
    def dev(self):
        return self.__dev

    def produce(self, password: str = None, **overrides):
        """Initialize a new character instance and return it"""
        if not self.dev:
            self.read_keyring()
            self.keyring.unlock(password=password)
        merged_parameters = {**self.static_payload, **self.dynamic_payload, **overrides}
        return self._character_class(**merged_parameters)

    @staticmethod
    def _read_configuration_file(filepath) -> dict:
        with open(filepath, 'r') as file:
            payload = NodeConfiguration.__CONFIG_FILE_DESERIALIZER(file.read())
        return payload

    @classmethod
    def from_configuration_file(cls, filepath, **overrides) -> 'NodeConfiguration':
        """Initialize a NodeConfiguration from a JSON file."""
        from nucypher.config.storages import NodeStorage  # TODO: move
        NODE_STORAGES = {storage_class._name: storage_class for storage_class in NodeStorage.__subclasses__()}

        payload = cls._read_configuration_file(filepath=filepath)

        # Make NodeStorage
        storage_payload = payload['node_storage']
        storage_type = storage_payload[NodeStorage._TYPE_LABEL]
        storage_class = NODE_STORAGES[storage_type]
        node_storage = storage_class.from_payload(payload=storage_payload,
                                                  character_class=cls._character_class,
                                                  federated_only=payload['federated_only'],
                                                  serializer=cls.NODE_SERIALIZER,
                                                  deserializer=cls.NODE_DESERIALIZER)

        payload.update(dict(node_storage=node_storage))
        return cls(is_me=True, **{**payload, **overrides})

    def to_configuration_file(self, filepath: str = None) -> str:
        """Write the static_payload to a JSON file."""
        if filepath is None:
            filename = '{}{}'.format(self._name.lower(), self.__CONFIG_FILE_EXT)
            filepath = os.path.join(self.config_root, filename)

        payload = self.static_payload
        del payload['is_me']  # TODO
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
                         registry_filepath=self.registry_filepath)
        return filepaths

    @classmethod
    def generate_runtime_filepaths(cls, config_root: str) -> dict:
        """Dynamically generate paths based on configuration root directory"""
        filepaths = dict(config_root=config_root,
                         config_file_location=os.path.join(config_root, cls.CONFIG_FILENAME),
                         keyring_dir=os.path.join(config_root, 'keyring'),
                         registry_filepath=os.path.join(config_root, NodeConfiguration.__REGISTRY_NAME))
        return filepaths

    def __cache_runtime_filepaths(self) -> None:
        """Generate runtime filepaths and cache them on the config object"""
        filepaths = self.generate_runtime_filepaths(config_root=self.config_root)
        for field, filepath in filepaths.items():
            if getattr(self, field) is UNINITIALIZED_CONFIGURATION:
                setattr(self, field, filepath)

    def derive_node_power_ups(self) -> List[CryptoPowerUp]:
        power_ups = list()
        if self.is_me and not self.dev:
            for power_class in self._character_class._default_crypto_powerups:
                power_up = self.keyring.derive_crypto_power(power_class)
                power_ups.append(power_up)
        return power_ups

    def initialize(self,
                   password: str,
                   no_registry: bool = False,
                   wallet: bool = False,
                   encrypting: bool = False,
                   tls: bool = False,
                   host: str = None,
                   curve=None,
                   no_keys: bool = False
                   ) -> str:
        """Initialize a new configuration."""

        #
        # Create Config Root
        #
        if self.__dev:
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

            # Node Storage
            self.node_storage.initialize()

            # Keyring
            os.mkdir(self.keyring_dir, mode=0o700)  # keyring TODO: Keyring backend entry point
            if not self.dev and not no_keys:
                # Keyring
                self.write_keyring(password=password,
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

        if not self.__dev:
            self.validate(config_root=self.config_root, no_registry=no_registry or self.federated_only)
        return self.config_root

    def read_known_nodes(self):
        self.known_nodes.update(self.node_storage.all(federated_only=self.federated_only))
        return self.known_nodes

    def read_keyring(self, *args, **kwargs):
        if self.checksum_address is None:
            raise self.ConfigurationError("No account specified to unlock keyring")
        self.keyring = NucypherKeyring(keyring_root=self.keyring_dir,
                                       account=self.checksum_address,
                                       *args, **kwargs)

    def write_keyring(self,
                      password: str,
                      encrypting: bool,
                      wallet: bool,
                      tls: bool,
                      host: str,
                      tls_curve: EllipticCurve = None,
                      ) -> NucypherKeyring:

        self.keyring = NucypherKeyring.generate(password=password,
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

        if not blank and not self.dev:
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
            self.log.warn("Writing blank registry")
            open(output_filepath, 'w').close()  # write blank

        self.log.debug("Successfully wrote registry to {}".format(output_filepath))
        return output_filepath
    
    def connect_to_blockchain(self, provider_uri: str, poa: bool, compile: bool):
        if self.federated_only:
            raise NodeConfiguration.ConfigurationError("Cannot connect to blockchain in federated mode")

        self.blockchain = Blockchain.connect(provider_uri=provider_uri, compile=compile)
        if poa is True:
            w3 = self.blockchain.interface.w3
            w3.middleware_stack.inject(geth_poa_middleware, layer=0)

        self.accounts = self.blockchain.interface.w3.eth.accounts
        self.log.debug("Established connection to provider {}".format(self.blockchain.interface.provider_uri))

    def connect_to_contracts(self) -> None:
        """Initialize contract agency and set them on config"""
        self.token_agent = NucypherTokenAgent(blockchain=self.blockchain)
        self.miner_agent = MinerAgent(blockchain=self.blockchain)
        self.policy_agent = PolicyAgent(blockchain=self.blockchain)
        self.log.debug("CLI established connection to nucypher contracts")
