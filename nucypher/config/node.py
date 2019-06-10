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


import binascii
import json
import os
import secrets
import string
from abc import ABC
from json import JSONDecodeError
from tempfile import TemporaryDirectory
from typing import List, Set

import eth_utils
from constant_sorrow.constants import (
    UNINITIALIZED_CONFIGURATION,
    STRANGER_CONFIGURATION,
    NO_BLOCKCHAIN_CONNECTION,
    LIVE_CONFIGURATION,
    NO_KEYRING_ATTACHED
)
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.ec import EllipticCurve
from cryptography.x509 import Certificate
from eth_utils import to_checksum_address, is_checksum_address
from twisted.logger import Logger
from umbral.signing import Signature

from nucypher.blockchain.eth.agents import PolicyAgent, StakingEscrowAgent, NucypherTokenAgent
from nucypher.blockchain.eth.chains import Blockchain
from nucypher.blockchain.eth.registry import EthereumContractRegistry
from nucypher.config.constants import DEFAULT_CONFIG_ROOT, BASE_DIR
from nucypher.config.keyring import NucypherKeyring
from nucypher.config.storages import NodeStorage, ForgetfulNodeStorage, LocalFileBasedNodeStorage
from nucypher.crypto.powers import CryptoPowerUp, CryptoPower
from nucypher.network.middleware import RestMiddleware
from nucypher.network.nodes import FleetStateTracker


class NodeConfiguration(ABC):
    """
    'Sideways Engagement' of Character classes; a reflection of input parameters.
    """

    # Abstract
    _NAME = NotImplemented
    _CHARACTER_CLASS = NotImplemented
    CONFIG_FILENAME = NotImplemented
    DEFAULT_CONFIG_FILE_LOCATION = NotImplemented

    # Mode
    DEFAULT_OPERATING_MODE = 'decentralized'

    # Domains
    DEFAULT_DOMAIN = 'goerli'

    # Serializers
    NODE_SERIALIZER = binascii.hexlify
    NODE_DESERIALIZER = binascii.unhexlify

    # System
    __CONFIG_FILE_EXT = '.config'
    __CONFIG_FILE_DESERIALIZER = json.loads
    TEMP_CONFIGURATION_DIR_PREFIX = "nucypher-tmp-"

    # Blockchain
    DEFAULT_PROVIDER_URI = 'http://localhost:8545'

    # Registry
    __REGISTRY_NAME = 'contract_registry.json'
    REGISTRY_SOURCE = os.path.join(BASE_DIR, __REGISTRY_NAME)

    # Rest + TLS
    DEFAULT_REST_HOST = '127.0.0.1'
    DEFAULT_REST_PORT = 9151
    DEFAULT_DEVELOPMENT_REST_PORT = 10151

    DEFAULT_CONTROLLER_PORT = NotImplemented

    __DEFAULT_TLS_CURVE = ec.SECP384R1
    __DEFAULT_NETWORK_MIDDLEWARE_CLASS = RestMiddleware

    class ConfigurationError(RuntimeError):
        pass

    class InvalidConfiguration(ConfigurationError):
        pass

    class NoConfigurationRoot(InvalidConfiguration):
        pass

    def __init__(self,

                 # Base
                 config_root: str = None,
                 config_file_location: str = None,

                 # Mode
                 dev_mode: bool = False,
                 federated_only: bool = False,

                 # Identity
                 is_me: bool = True,
                 checksum_address: str = None,
                 crypto_power: CryptoPower = None,

                 # Keyring
                 keyring: NucypherKeyring = None,
                 keyring_dir: str = None,

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
                 registry_source: str = None,
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

        self.interface_signature = interface_signature
        self.crypto_power = crypto_power

        #
        # Keyring
        #
        self.keyring = keyring or NO_KEYRING_ATTACHED
        self.keyring_dir = keyring_dir or UNINITIALIZED_CONFIGURATION

        # Contract Registry
        self.download_registry = download_registry
        self.__registry_source = registry_source or self.REGISTRY_SOURCE
        self.registry_filepath = registry_filepath or UNINITIALIZED_CONFIGURATION

        #
        # Configuration
        #
        self.config_file_location = config_file_location or UNINITIALIZED_CONFIGURATION
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
            self.config_root = config_root or DEFAULT_CONFIG_ROOT
            self._cache_runtime_filepaths()
            self.node_storage = node_storage or LocalFileBasedNodeStorage(federated_only=federated_only,
                                                                          config_root=self.config_root)

        # Domains
        self.domains = domains or {self.DEFAULT_DOMAIN}

        #
        # Identity
        #
        self.is_me = is_me
        self.checksum_address = checksum_address

        if self.is_me is True or dev_mode is True:
            # Self
            if self.checksum_address and dev_mode is False:
                self.attach_keyring()
            self.network_middleware = network_middleware or self.__DEFAULT_NETWORK_MIDDLEWARE_CLASS()

        else:
            # Stranger
            self.node_storage = STRANGER_CONFIGURATION
            self.keyring_dir = STRANGER_CONFIGURATION
            self.keyring = STRANGER_CONFIGURATION
            self.network_middleware = STRANGER_CONFIGURATION
            if network_middleware:
                raise self.ConfigurationError("Cannot configure a stranger to use network middleware.")

        #
        # Learner
        #
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
            self.initialize(password=password, download_registry=download_registry)

    def __call__(self, *args, **kwargs):
        return self.produce(*args, **kwargs)

    @classmethod
    def generate(cls, password: str, *args, **kwargs):
        """Shortcut: Hook-up a new initial installation and write configuration file to the disk"""
        node_config = cls(dev_mode=False, is_me=True, *args, **kwargs)
        node_config.__write(password=password)
        return node_config

    def __write(self, password: str):
        _new_installation_path = self.initialize(password=password, download_registry=self.download_registry)
        _configuration_filepath = self.to_configuration_file(filepath=self.config_file_location)

    def cleanup(self) -> None:
        if self.__dev_mode:
            self.__temp_dir.cleanup()
        if self.blockchain:
            self.blockchain.disconnect()

    @property
    def dev_mode(self):
        return self.__dev_mode

    @property
    def known_nodes(self):
        return self.__fleet_state

    def connect_to_blockchain(self,
                              enode: str = None,
                              recompile_contracts: bool = False,
                              full_sync: bool = False) -> None:
        """

        :param enode: ETH seednode or bootnode enode address to start learning from,
                      i.e. 'enode://e54eebad24dc...e1f6d246bea455@52.71.255.237:30303'

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

        # Add Ethereum Peer
        if enode:
            if self.blockchain.interface.client_version == 'geth':
                self.blockchain.interface.w3.geth.admin.addPeer(enode)
            else:
                raise NotImplementedError

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
        merged_parameters = {**self.static_payload, **self.dynamic_payload, **overrides}
        non_init_params = ('config_root', 'poa', 'provider_uri')
        character_init_params = filter(lambda t: t[0] not in non_init_params, merged_parameters.items())
        return dict(character_init_params)

    def produce(self, **overrides):
        """Initialize a new character instance and return it."""
        merged_parameters = self.generate_parameters(**overrides)
        character = self._CHARACTER_CLASS(**merged_parameters)
        return character

    @staticmethod
    def _read_configuration_file(filepath: str) -> dict:
        try:
            with open(filepath, 'r') as file:
                raw_contents = file.read()
                payload = NodeConfiguration.__CONFIG_FILE_DESERIALIZER(raw_contents)
        except FileNotFoundError:
            raise
        return payload

    @classmethod
    def get_configuration_payload(cls, filepath: str = None, **overrides) -> dict:

        from nucypher.config.storages import NodeStorage
        node_storage_subclasses = {storage._name: storage for storage in NodeStorage.__subclasses__()}

        if filepath is None:
            filepath = cls.DEFAULT_CONFIG_FILE_LOCATION

        # Read from disk
        payload = cls._read_configuration_file(filepath=filepath)

        # Sanity check
        try:
            checksum_address = payload['checksum_address']
        except KeyError:
            raise cls.ConfigurationError(f"No checksum address specified in configuration file {filepath}")
        else:
            if not eth_utils.is_checksum_address(checksum_address):
                raise cls.ConfigurationError(f"Address: '{checksum_address}', specified in {filepath} is not a valid checksum address.")

        # Initialize NodeStorage subclass from file (sub-configuration)
        storage_payload = payload['node_storage']
        storage_type = storage_payload[NodeStorage._TYPE_LABEL]
        storage_class = node_storage_subclasses[storage_type]
        node_storage = storage_class.from_payload(payload=storage_payload,
                                                  federated_only=payload['federated_only'],
                                                  serializer=cls.NODE_SERIALIZER,
                                                  deserializer=cls.NODE_DESERIALIZER)

        domains = set(payload['domains'])
        payload.update(dict(node_storage=node_storage, domains=domains))

        # Filter out Nones from overrides to detect, well, overrides
        overrides = {k: v for k, v in overrides.items() if v is not None}

        payload = {**payload, **overrides}
        return payload

    @classmethod
    def from_configuration_file(cls,
                                filepath: str = None,
                                provider_process=None,
                                **overrides) -> 'NodeConfiguration':

        """Initialize a NodeConfiguration from a JSON file."""

        payload = cls.get_configuration_payload(filepath=filepath, **overrides)

        # Instantiate from merged params
        node_configuration = cls(config_file_location=filepath,
                                 provider_process=provider_process,
                                 **payload)

        return node_configuration

    def to_configuration_file(self, filepath: str = None) -> str:
        """Write the static_payload to a JSON file."""
        if not filepath:
            filepath = os.path.join(self.config_root, self.CONFIG_FILENAME)

        if os.path.isfile(filepath):
            # Avoid overriding an existing default configuration
            filename = f'{self._NAME.lower()}-{self.checksum_address[:6]}{self.__CONFIG_FILE_EXT}'
            filepath = os.path.join(self.config_root, filename)

        payload = self.static_payload
        del payload['is_me']

        # Save node connection data
        payload.update(dict(node_storage=self.node_storage.payload(), domains=list(self.domains)))

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
                message = 'Missing configuration file or directory: {}.'
                if 'registry' in path:
                    message += ' Did you mean to pass --federated-only?'                    
                raise NodeConfiguration.InvalidConfiguration(message.format(path))
        return True

    @property
    def static_payload(self) -> dict:
        """Exported static configuration values for initializing Ursula"""
        payload = dict(
            config_root=self.config_root,

            # Identity
            is_me=self.is_me,
            federated_only=self.federated_only,
            checksum_address=self.checksum_address,
            keyring_dir=self.keyring_dir,

            # Behavior
            domains=self.domains,  # From Set
            provider_uri=self.provider_uri,
            learn_on_same_thread=self.learn_on_same_thread,
            abort_on_learning_error=self.abort_on_learning_error,
            start_learning_now=self.start_learning_now,
            save_metadata=self.save_metadata,
        )

        if not self.federated_only:
            payload.update(dict(provider_uri=self.provider_uri, poa=self.poa))

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

    def _cache_runtime_filepaths(self) -> None:
        """Generate runtime filepaths and cache them on the config object"""
        filepaths = self.generate_runtime_filepaths(config_root=self.config_root)
        for field, filepath in filepaths.items():
            if getattr(self, field) is UNINITIALIZED_CONFIGURATION:
                setattr(self, field, filepath)

    def derive_node_power_ups(self) -> List[CryptoPowerUp]:
        power_ups = list()
        if self.is_me and not self.dev_mode:
            for power_class in self._CHARACTER_CLASS._default_crypto_powerups:
                power_up = self.keyring.derive_crypto_power(power_class)
                power_ups.append(power_up)
        return power_ups

    def initialize(self, password: str, download_registry: bool = True) -> str:
        """Initialize a new configuration and write installation files to disk."""

        #
        # Create Base System Filepaths
        #

        if self.__dev_mode:
            self.__temp_dir = TemporaryDirectory(prefix=self.TEMP_CONFIGURATION_DIR_PREFIX)
            self.config_root = self.__temp_dir.name
        else:

            # Production Configuration
            try:
                os.mkdir(self.config_root, mode=0o755)

            except FileExistsError:
                if os.listdir(self.config_root):
                    message = "There are existing files located at {}".format(self.config_root)
                    self.log.debug(message)

            except FileNotFoundError:
                os.makedirs(self.config_root, mode=0o755)

        # Generate Installation Subdirectories
        self._cache_runtime_filepaths()

        #
        # Node Storage
        #

        self.node_storage.initialize()

        #
        # Keyring
        #

        if not self.dev_mode:
            if not os.path.isdir(self.keyring_dir):
                os.mkdir(self.keyring_dir, mode=0o700)  # TODO: Keyring backend entry point - COS
            self.write_keyring(password=password)

        #
        # Registry
        #

        if download_registry and not self.federated_only:
            self.registry_filepath = EthereumContractRegistry.download_latest_publication()

        #
        # Verify
        #

        if not self.__dev_mode:
            self.validate(config_root=self.config_root, no_registry=(not download_registry) or self.federated_only)

        #
        # Success
        #

        message = "Created nucypher installation files at {}".format(self.config_root)
        self.log.debug(message)

        return self.config_root

    def attach_keyring(self, checksum_address: str = None, *args, **kwargs) -> None:
        if self.keyring is not NO_KEYRING_ATTACHED:
            if self.keyring.checksum_address != (checksum_address or self.checksum_address):
                raise self.ConfigurationError("There is already a keyring attached to this configuration.")
            return

        if (checksum_address or self.checksum_address) is None:
            raise self.ConfigurationError("No account specified to unlock keyring")

        self.keyring = NucypherKeyring(keyring_root=self.keyring_dir,  # type: str
                                       account=checksum_address or self.checksum_address,  # type: str
                                       *args, **kwargs)

    def write_keyring(self, password: str, wallet: bool = True, **generation_kwargs) -> NucypherKeyring:

        checksum_address = None

        #
        # Decentralized
        #
        if wallet:

            # Note: It is assumed the blockchain is not yet available.
            if not self.federated_only and not self.checksum_address:

                # "Casual Geth"
                if self.provider_process:

                    if not os.path.exists(self.provider_process.data_dir):
                        os.mkdir(self.provider_process.data_dir)

                    # Get or create wallet address (geth etherbase)
                    checksum_address = self.provider_process.ensure_account_exists(password=password)

                # "Formal Geth" - Manual Web3 Provider, We assume is already running and available
                else:
                    self.connect_to_blockchain()
                    if not self.blockchain.interface.client.accounts:
                        raise self.ConfigurationError(f'Web3 provider "{self.provider_uri}" does not have any accounts')
                    checksum_address = self.blockchain.interface.client.etherbase

                # Addresses read from some node keyrings (clients) are *not* returned in checksum format.
                checksum_address = to_checksum_address(checksum_address)

            # Use explicit address
            elif self.checksum_address:
                checksum_address = self.checksum_address

        self.keyring = NucypherKeyring.generate(password=password,
                                                keyring_root=self.keyring_dir,
                                                checksum_address=checksum_address,
                                                **generation_kwargs)
        # Operating mode switch
        if self.federated_only or not wallet:
            self.checksum_address = self.keyring.federated_address
        else:
            self.checksum_address = self.keyring.account

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

        if not blank and not self.dev_mode:
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
