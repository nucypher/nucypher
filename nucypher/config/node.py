"""
This file is part of nucypher.

nucypher is free software: you can redistribute it and/or modify
it under the terms of the GNU Affero General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

nucypher is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU Affero General Public License for more details.

You should have received a copy of the GNU Affero General Public License
along with nucypher.  If not, see <https://www.gnu.org/licenses/>.
"""

import os
import secrets
import string
from tempfile import TemporaryDirectory
from typing import List, Set

import binascii
from constant_sorrow.constants import (
    UNINITIALIZED_CONFIGURATION,
    NO_BLOCKCHAIN_CONNECTION,
    LIVE_CONFIGURATION,
    NO_KEYRING_ATTACHED
)
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.ec import EllipticCurve
from cryptography.x509 import Certificate
from twisted.logger import Logger
from umbral.signing import Signature

from nucypher.blockchain.eth.agents import PolicyAgent, StakingEscrowAgent, NucypherTokenAgent
from nucypher.blockchain.eth.chains import Blockchain
from nucypher.blockchain.eth.registry import EthereumContractRegistry
from nucypher.config.base import BaseConfiguration
from nucypher.config.constants import BASE_DIR
from nucypher.config.keyring import NucypherKeyring
from nucypher.config.storages import NodeStorage, ForgetfulNodeStorage, LocalFileBasedNodeStorage
from nucypher.crypto.powers import CryptoPowerUp, CryptoPower
from nucypher.network.middleware import RestMiddleware
from nucypher.network.nodes import FleetStateTracker


class NodeConfiguration(BaseConfiguration):
    """
    'Sideways Engagement' of Character classes; a reflection of input parameters.
    """

    # Abstract
    _CHARACTER_CLASS = NotImplemented

    TEMP_CONFIGURATION_DIR_PREFIX = 'tmp-nucypher'

    # Mode
    DEFAULT_OPERATING_MODE = 'decentralized'

    # Domains
    DEFAULT_DOMAIN = 'goerli'

    # Serializers
    NODE_SERIALIZER = binascii.hexlify
    NODE_DESERIALIZER = binascii.unhexlify

    # Blockchain
    DEFAULT_PROVIDER_URI = 'http://localhost:8545'

    # Rest + TLS
    DEFAULT_REST_HOST = '127.0.0.1'
    DEFAULT_REST_PORT = 9151
    DEFAULT_DEVELOPMENT_REST_PORT = 10151

    DEFAULT_CONTROLLER_PORT = NotImplemented

    __DEFAULT_TLS_CURVE = ec.SECP384R1
    __DEFAULT_NETWORK_MIDDLEWARE_CLASS = RestMiddleware

    def __init__(self,

                 # Base
                 config_root: str = None,
                 filepath: str = None,

                 # Mode
                 dev_mode: bool = False,
                 federated_only: bool = False,

                 # Identity
                 checksum_address: str = None,
                 crypto_power: CryptoPower = None,

                 # Keyring
                 keyring: NucypherKeyring = None,
                 keyring_root: str = None,

                 # Learner
                 learn_on_same_thread: bool = False,
                 abort_on_learning_error: bool = False,
                 start_learning_now: bool = True,

                 # REST
                 rest_host: str = None,
                 rest_port: int = None,
                 controller_port: int = None,

                 # TLS
                 tls_curve: EllipticCurve = None,
                 certificate: Certificate = None,

                 # Network
                 domains: Set[str] = None,
                 interface_signature: Signature = None,
                 network_middleware: RestMiddleware = None,

                 # Node Storage
                 known_nodes: set = None,
                 node_storage: NodeStorage = None,
                 reload_metadata: bool = True,
                 save_metadata: bool = True,

                 # Blockchain
                 poa: bool = False,
                 provider_uri: str = None,
                 provider_process = None,

                 # Registry
                 registry_filepath: str = None,
                 download_registry: bool = True

                 ) -> None:

        # Logs
        self.log = Logger(self.__class__.__name__)

        #
        # REST + TLS + Web
        #
        self.controller_port = controller_port or self.DEFAULT_CONTROLLER_PORT
        self.rest_host = rest_host or self.DEFAULT_REST_HOST
        default_port = (self.DEFAULT_DEVELOPMENT_REST_PORT if dev_mode else self.DEFAULT_REST_PORT)
        self.rest_port = rest_port or default_port
        self.tls_curve = tls_curve or self.__DEFAULT_TLS_CURVE
        self.certificate = certificate

        self.network_middleware = network_middleware or self.__DEFAULT_NETWORK_MIDDLEWARE_CLASS()

        self.interface_signature = interface_signature
        self.crypto_power = crypto_power

        #
        # Keyring
        #
        self.keyring = keyring or NO_KEYRING_ATTACHED
        self.keyring_root = keyring_root or UNINITIALIZED_CONFIGURATION

        # Contract Registry
        self.download_registry = download_registry
        self.registry_filepath = registry_filepath or UNINITIALIZED_CONFIGURATION

        #
        # Configuration
        #
        self.config_file_location = filepath or UNINITIALIZED_CONFIGURATION
        self.config_root = UNINITIALIZED_CONFIGURATION

        #
        # Mode
        #
        self.federated_only = federated_only
        self.__dev_mode = dev_mode

        if self.__dev_mode:
            self.__temp_dir = UNINITIALIZED_CONFIGURATION
            self.node_storage = ForgetfulNodeStorage(federated_only=federated_only, character_class=self.__class__)
        else:
            self.__temp_dir = LIVE_CONFIGURATION
            self.config_root = config_root or self.DEFAULT_CONFIG_ROOT
            self._cache_runtime_filepaths()
            self.node_storage = node_storage or LocalFileBasedNodeStorage(federated_only=federated_only,
                                                                          config_root=self.config_root)

        #
        # Identity
        #
        self.is_me = True  # NodeConfigurations can only be used with Self-Characters
        self.checksum_address = checksum_address
        if not dev_mode and checksum_address:
            self.attach_keyring()

        #
        # Learner
        #

        self.domains = domains or {self.DEFAULT_DOMAIN}
        self.learn_on_same_thread = learn_on_same_thread
        self.abort_on_learning_error = abort_on_learning_error
        self.start_learning_now = start_learning_now
        self.save_metadata = save_metadata
        self.reload_metadata = reload_metadata

        self.__fleet_state = FleetStateTracker()
        known_nodes = known_nodes or set()
        if known_nodes:
            self.known_nodes._nodes.update({node.checksum_address: node for node in known_nodes})
            self.known_nodes.record_fleet_state()  # TODO: Does this call need to be here?

        #
        # Blockchain
        #
        self.poa = poa
        self.provider_uri = provider_uri or self.DEFAULT_PROVIDER_URI
        self.provider_process = provider_process or NO_BLOCKCHAIN_CONNECTION
        self.blockchain = NO_BLOCKCHAIN_CONNECTION.bool_value(False)
        self.accounts = NO_BLOCKCHAIN_CONNECTION
        self.token_agent = NO_BLOCKCHAIN_CONNECTION
        self.staking_agent = NO_BLOCKCHAIN_CONNECTION
        self.policy_agent = NO_BLOCKCHAIN_CONNECTION

        #
        # Development Mode
        #

        if dev_mode:

            # Ephemeral dev settings
            self.abort_on_learning_error = True
            self.save_metadata = False
            self.reload_metadata = False

            # Generate one-time alphanumeric development password
            alphabet = string.ascii_letters + string.digits
            password = ''.join(secrets.choice(alphabet) for _ in range(32))

            # Auto-initialize
            self.initialize(password=password)

        super().__init__(filepath=self.config_file_location, config_root=self.config_root)

    def __call__(self, *args, **kwargs):
        return self.produce(*args, **kwargs)

    @classmethod
    def generate(cls, password: str, *args, **kwargs):
        """Shortcut: Hook-up a new initial installation and write configuration file to the disk"""
        node_config = cls(dev_mode=False, *args, **kwargs)
        node_config.initialize(password=password)
        node_config.to_configuration_file(modifier=node_config.checksum_address)
        return node_config

    def cleanup(self) -> None:
        if self.__dev_mode:
            self.__temp_dir.cleanup()
        if self.blockchain:
            self.blockchain.disconnect()

    @property
    def dev_mode(self) -> bool:
        return self.__dev_mode

    @property
    def known_nodes(self):
        return self.__fleet_state

    def connect_to_blockchain(self,
                              recompile_contracts: bool = False,
                              full_sync: bool = False) -> None:
        """
        :param recompile_contracts: Recompile all contracts on connection.
        :return: None
        """
        if self.federated_only:
            raise NodeConfiguration.ConfigurationError("Cannot connect to blockchain in federated mode")

        self.blockchain = Blockchain.connect(provider_uri=self.provider_uri,
                                             compile=recompile_contracts,
                                             poa=self.poa,
                                             fetch_registry=True,
                                             provider_process=self.provider_process,
                                             sync=full_sync)

        # Read Ethereum Node Keyring
        self.accounts = self.blockchain.interface.w3.eth.accounts

    def connect_to_contracts(self) -> None:
        """Initialize contract agency and set them on config"""
        self.token_agent = NucypherTokenAgent(blockchain=self.blockchain)
        self.staking_agent = StakingEscrowAgent(blockchain=self.blockchain)
        self.policy_agent = PolicyAgent(blockchain=self.blockchain)
        self.log.debug("Established connection to nucypher contracts")

    def read_known_nodes(self):
        known_nodes = self.node_storage.all(federated_only=self.federated_only)
        known_nodes = {node.checksum_address: node for node in known_nodes}
        self.known_nodes._nodes.update(known_nodes)
        self.known_nodes.record_fleet_state()
        return self.known_nodes

    def forget_nodes(self) -> None:
        self.node_storage.clear()
        message = "Removed all stored node node metadata and certificates"
        self.log.debug(message)

    def destroy(self) -> None:
        """Parse a node configuration and remove all associated files from the filesystem"""
        self.keyring.destroy()
        os.remove(self.config_file_location)

    def generate_parameters(self, **overrides) -> dict:
        merged_parameters = {**self.static_payload(), **self.dynamic_payload, **overrides}
        non_init_params = ('config_root', 'poa', 'provider_uri')
        character_init_params = filter(lambda t: t[0] not in non_init_params, merged_parameters.items())
        return dict(character_init_params)

    def produce(self, **overrides):
        """Initialize a new character instance and return it."""
        merged_parameters = self.generate_parameters(**overrides)
        character = self._CHARACTER_CLASS(**merged_parameters)
        return character

    @classmethod
    def assemble(cls, filepath: str = None, **overrides):

        # Understand this to be a dynamic payload now
        payload = cls._read_configuration_file(filepath=filepath)

        # Storage
        node_storage = cls.load_node_storage(storage_payload=payload['node_storage'],
                                             federated_only=payload['federated_only'])

        # Domains
        domains = set(payload['domains'])

        # Assemble
        payload.update(dict(node_storage=node_storage, domains=domains))

        # Filter out Nones from overrides to detect, well, overrides
        # Acts as a shim for optional CLI flags
        overrides = {k: v for k, v in overrides.items() if v is not None}

        payload = {**payload, **overrides}
        return payload

    @classmethod
    def from_configuration_file(cls,
                                filepath: str = None,
                                provider_process=None,
                                **overrides) -> 'NodeConfiguration':

        """Initialize a NodeConfiguration from a JSON file."""

        # Read from disk
        filepath = filepath or cls.default_filepath()

        # Instantiate from assembled params
        assembled_params = cls.assemble(filepath=filepath, **overrides)
        node_configuration = cls(filepath=filepath, provider_process=provider_process, **assembled_params)

        return node_configuration

    def generate_filepath(self, filepath: str = None, modifier: str = None, override: bool = False) -> str:
        filepath = super().generate_filepath(filepath=filepath,
                                             modifier=modifier or self.checksum_address,
                                             override=override)
        self.filepath = filepath
        return filepath

    def validate(self, config_root: str, no_registry: bool = False) -> bool:

        # Top-level
        if not os.path.exists(config_root):
            raise self.ConfigurationError('No configuration directory found at {}.'.format(config_root))

        # Sub-paths
        filepaths = self.runtime_filepaths
        if no_registry:
            del filepaths['registry_filepath']

        for field, path in filepaths.items():
            if not os.path.exists(path):
                message = 'Missing configuration file or directory: {}.'
                if 'registry' in path:
                    message += ' Did you mean to pass --federated-only?'                    
                raise NodeConfiguration.InvalidConfiguration(message.format(path))
        return True

    def static_payload(self) -> dict:
        """Exported static configuration values for initializing Ursula"""

        base_payload = super().static_payload()

        payload = dict(

            # Identity
            federated_only=self.federated_only,
            checksum_address=self.checksum_address,
            keyring_root=self.keyring_root,

            # Behavior
            domains=list(self.domains),  # From Set
            provider_uri=self.provider_uri,
            learn_on_same_thread=self.learn_on_same_thread,
            abort_on_learning_error=self.abort_on_learning_error,
            start_learning_now=self.start_learning_now,
            save_metadata=self.save_metadata,
            node_storage=self.node_storage.payload(),
        )

        # Optional values (mode)
        if not self.federated_only:
            payload.update(dict(provider_uri=self.provider_uri, poa=self.poa))

        # Merge with base payload
        base_payload.update(payload)

        return payload

    @property
    def dynamic_payload(self, connect_to_blockchain: bool = True, **overrides) -> dict:
        """Exported dynamic configuration values for initializing Ursula"""

        if self.reload_metadata:
            known_nodes = self.node_storage.all(federated_only=self.federated_only)
            known_nodes = {node.checksum_address: node for node in known_nodes}
            self.known_nodes._nodes.update(known_nodes)
        self.known_nodes.record_fleet_state()

        payload = dict(network_middleware=self.network_middleware or self.__DEFAULT_NETWORK_MIDDLEWARE_CLASS(),
                       known_nodes=self.known_nodes,
                       node_storage=self.node_storage,
                       crypto_power_ups=self.derive_node_power_ups() or None)

        if not self.federated_only and connect_to_blockchain:
            self.connect_to_blockchain(recompile_contracts=False)
            payload.update(blockchain=self.blockchain)

        if overrides:
            self.log.debug("Overrides supplied to dynamic payload for {}".format(self.__class__.__name__))
            payload.update(overrides)

        return payload

    @property
    def runtime_filepaths(self):
        filepaths = dict(config_root=self.config_root,
                         keyring_root=self.keyring_root,
                         registry_filepath=self.registry_filepath)
        return filepaths

    @classmethod
    def generate_runtime_filepaths(cls, config_root: str) -> dict:
        """Dynamically generate paths based on configuration root directory"""
        filepaths = dict(config_root=config_root,
                         config_file_location=os.path.join(config_root, cls.generate_filename()),
                         keyring_root=os.path.join(config_root, 'keyring'),
                         registry_filepath=os.path.join(config_root, EthereumContractRegistry.REGISTRY_NAME))
        return filepaths

    def _cache_runtime_filepaths(self) -> None:
        """Generate runtime filepaths and cache them on the config object"""
        filepaths = self.generate_runtime_filepaths(config_root=self.config_root)
        for field, filepath in filepaths.items():
            if getattr(self, field) is UNINITIALIZED_CONFIGURATION:
                setattr(self, field, filepath)

    def attach_keyring(self, checksum_address: str = None, *args, **kwargs) -> None:
        if self.keyring is not NO_KEYRING_ATTACHED:
            if self.keyring.checksum_address != (checksum_address or self.checksum_address):
                raise self.ConfigurationError("There is already a keyring attached to this configuration.")
            return

        if (checksum_address or self.checksum_address) is None:
            raise self.ConfigurationError("No account specified to unlock keyring")

        self.keyring = NucypherKeyring(keyring_root=self.keyring_root,  # type: str
                                       account=checksum_address or self.checksum_address,  # type: str
                                       *args, **kwargs)

    def derive_node_power_ups(self) -> List[CryptoPowerUp]:
        power_ups = list()
        if self.is_me and not self.dev_mode:
            for power_class in self._CHARACTER_CLASS._default_crypto_powerups:
                power_up = self.keyring.derive_crypto_power(power_class)
                power_ups.append(power_up)
        return power_ups

    def write_config_root(self):
        # Production Configuration
        try:
            os.mkdir(self.config_root, mode=0o755)

        except FileExistsError:
            if os.listdir(self.config_root):
                message = "There are existing files located at {}".format(self.config_root)
                self.log.debug(message)

        except FileNotFoundError:
            os.makedirs(self.config_root, mode=0o755)

    def initialize(self, password: str) -> str:
        """Initialize a new configuration and write installation files to disk."""

        # Configuration Root
        if self.__dev_mode:
            self.__temp_dir = TemporaryDirectory(prefix=self.TEMP_CONFIGURATION_DIR_PREFIX)
            self.config_root = self.__temp_dir.name

        else:
            self.write_config_root()

            # Keyring
            self.write_keyring(password=password)

        # Generate Installation Subdirectories
        self._cache_runtime_filepaths()

        # Node Storage
        self.node_storage.initialize()

        # Registry
        if self.download_registry:
            self.registry_filepath = EthereumContractRegistry.download_latest_publication()

        # Validate
        if not self.__dev_mode:
            self.validate(config_root=self.config_root,
                          no_registry=(not self.download_registry) or self.federated_only)

        # Success
        message = "Created nucypher installation files at {}".format(self.config_root)
        self.log.debug(message)
        return self.config_root

    def write_keyring(self,
                      password: str,
                      **generation_kwargs) -> NucypherKeyring:

        # Note: It is assumed the blockchain is not yet available.
        if not self.federated_only:

            if self.provider_process:

                # Generate Geth's "datadir"
                if not os.path.exists(self.provider_process.data_dir):
                    os.mkdir(self.provider_process.data_dir)

                # Get or create wallet address
                if not self.checksum_address:
                    self.checksum_address = self.provider_process.ensure_account_exists(password=password)
                elif self.checksum_address not in self.provider_process.accounts():
                    raise self.ConfigurationError(f'Unknown Account {self.checksum_address}')

            # Determine etherbase (web3)
            elif not self.checksum_address:
                self.connect_to_blockchain()
                if not self.blockchain.interface.w3.eth.accounts:
                    raise self.ConfigurationError(f'Web3 provider "{self.provider_uri}" does not have any accounts')
                self.checksum_address = self.blockchain.interface.w3.eth.accounts[0]

        self.keyring = NucypherKeyring.generate(password=password,
                                                keyring_root=self.keyring_root,
                                                checksum_address=self.checksum_address,
                                                federated=self.federated_only,
                                                **generation_kwargs)

        self.checksum_address = self.keyring.account
        return self.keyring

    @classmethod
    def load_node_storage(cls, storage_payload: dict, federated_only: bool):

        # Initialize NodeStorage subclass from file (sub-configuration)
        from nucypher.config.storages import NodeStorage
        node_storage_subclasses = {storage._name: storage for storage in NodeStorage.__subclasses__()}

        storage_type = storage_payload[NodeStorage._TYPE_LABEL]
        storage_class = node_storage_subclasses[storage_type]

        node_storage = storage_class.from_payload(payload=storage_payload,
                                                  federated_only=federated_only,
                                                  serializer=cls.NODE_SERIALIZER,
                                                  deserializer=cls.NODE_DESERIALIZER)

        return node_storage