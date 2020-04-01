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
from tempfile import TemporaryDirectory
from typing import List, Set, Union, Callable

from constant_sorrow.constants import (
    UNINITIALIZED_CONFIGURATION,
    NO_BLOCKCHAIN_CONNECTION,
    LIVE_CONFIGURATION,
    NO_KEYRING_ATTACHED,
    DEVELOPMENT_CONFIGURATION,
    FEDERATED_ADDRESS
)
from twisted.logger import Logger
from umbral.signing import Signature

from nucypher.blockchain.eth.interfaces import BlockchainInterfaceFactory
from nucypher.blockchain.eth.networks import NetworksInventory
from nucypher.blockchain.eth.registry import (
    BaseContractRegistry,
    InMemoryContractRegistry,
    LocalContractRegistry
)
from nucypher.blockchain.eth.signers import Signer
from nucypher.config.base import BaseConfiguration
from nucypher.config.keyring import NucypherKeyring
from nucypher.config.storages import NodeStorage, ForgetfulNodeStorage, LocalFileBasedNodeStorage
from nucypher.crypto.powers import CryptoPowerUp, CryptoPower
from nucypher.network.middleware import RestMiddleware


# TODO: Relocate - #1575
class CharacterConfiguration(BaseConfiguration):
    """
    'Sideways Engagement' of Character classes; a reflection of input parameters.
    """

    VERSION = 1  # bump when static payload scheme changes

    CHARACTER_CLASS = NotImplemented
    DEFAULT_CONTROLLER_PORT = NotImplemented
    DEFAULT_DOMAIN = NetworksInventory.DEFAULT
    DEFAULT_NETWORK_MIDDLEWARE = RestMiddleware
    TEMP_CONFIGURATION_DIR_PREFIX = 'tmp-nucypher'

    # Gas
    DEFAULT_GAS_STRATEGY = 'fast'

    def __init__(self,

                 # Base
                 emitter=None,
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

                 # Network
                 controller_port: int = None,
                 domains: Set[str] = None,  # TODO: Mapping between learning domains and "registry" domains - #1580
                 interface_signature: Signature = None,
                 network_middleware: RestMiddleware = None,

                 # Node Storage
                 known_nodes: set = None,
                 node_storage: NodeStorage = None,
                 reload_metadata: bool = True,
                 save_metadata: bool = True,

                 # Blockchain
                 poa: bool = False,
                 light: bool = False,
                 sync: bool = False,
                 provider_uri: str = None,
                 provider_process=None,
                 gas_strategy: Union[Callable, str] = DEFAULT_GAS_STRATEGY,
                 signer_uri: str = None,

                 # Registry
                 registry: BaseContractRegistry = None,
                 registry_filepath: str = None):

        self.log = Logger(self.__class__.__name__)
        UNINITIALIZED_CONFIGURATION.bool_value(False)

        # Identity
        # NOTE: NodeConfigurations can only be used with Self-Characters
        self.is_me = True
        self.checksum_address = checksum_address

        # Keyring
        self.crypto_power = crypto_power
        self.keyring = keyring or NO_KEYRING_ATTACHED
        self.keyring_root = keyring_root or UNINITIALIZED_CONFIGURATION

        # Contract Registry
        if registry and registry_filepath:
            if registry.filepath != registry_filepath:
                error = f"Inconsistent registry filepaths for '{registry.filepath}' and '{registry_filepath}'."
                raise ValueError(error)
            else:
                self.log.warn(f"Registry and registry filepath were both passed.")
        self.registry = registry or NO_BLOCKCHAIN_CONNECTION.bool_value(False)
        self.registry_filepath = registry_filepath or UNINITIALIZED_CONFIGURATION

        # Blockchain
        self.poa = poa
        self.is_light = light
        self.provider_uri = provider_uri or NO_BLOCKCHAIN_CONNECTION
        self.provider_process = provider_process or NO_BLOCKCHAIN_CONNECTION
        self.signer_uri = signer_uri or NO_BLOCKCHAIN_CONNECTION

        # Learner
        self.federated_only = federated_only
        self.domains = domains or {self.DEFAULT_DOMAIN}
        self.learn_on_same_thread = learn_on_same_thread
        self.abort_on_learning_error = abort_on_learning_error
        self.start_learning_now = start_learning_now
        self.save_metadata = save_metadata
        self.reload_metadata = reload_metadata
        self.known_nodes = known_nodes or set()  # handpicked

        # Configuration
        self.__dev_mode = dev_mode
        self.config_file_location = filepath or UNINITIALIZED_CONFIGURATION
        self.config_root = UNINITIALIZED_CONFIGURATION

        #
        # Federated vs. Blockchain arguments consistency
        #

        #
        # Federated
        #

        if self.federated_only:
            # Check for incompatible values
            blockchain_args = {'filepath': registry_filepath,
                               'poa': poa,
                               'provider_process': provider_process,
                               'provider_uri': provider_uri,
                               'gas_strategy': gas_strategy}
            if any(blockchain_args.values()):
                bad_args = (f"{arg}={val}" for arg, val in blockchain_args.items() if val)
                self.log.warn(f"Arguments {bad_args} are incompatible with federated_only. "
                              f"Overridden with a sane default.")

                # Clear decentralized attributes to ensure consistency with a
                # federated configuration.
                self.poa = False
                self.is_light = False
                self.provider_uri = None
                self.provider_process = None
                self.registry_filepath = None
                self.gas_strategy = None

        #
        # Decentralized
        #

        else:
            self.gas_strategy = gas_strategy
            is_initialized = BlockchainInterfaceFactory.is_interface_initialized(provider_uri=self.provider_uri)
            if not is_initialized and provider_uri:
                BlockchainInterfaceFactory.initialize_interface(provider_uri=self.provider_uri,
                                                                poa=self.poa,
                                                                light=self.is_light,
                                                                provider_process=self.provider_process,
                                                                sync=sync,
                                                                emitter=emitter,
                                                                gas_strategy=gas_strategy)
            else:
                self.log.warn(f"Using existing blockchain interface connection ({self.provider_uri}).")

            if not self.registry:
                # TODO: These two code blocks are untested.
                if not self.registry_filepath:  # TODO: Registry URI  (goerli://speedynet.json) :-)
                    self.log.info(f"Fetching latest registry from source.")
                    self.registry = InMemoryContractRegistry.from_latest_publication(network=list(self.domains)[0])  # TODO: #1580
                else:
                    self.registry = LocalContractRegistry(filepath=self.registry_filepath)
                    self.log.info(f"Using local registry ({self.registry}).")

        if dev_mode:
            self.__temp_dir = UNINITIALIZED_CONFIGURATION
            self.__setup_node_storage()
            self.initialize(password=DEVELOPMENT_CONFIGURATION)
        else:
            self.__temp_dir = LIVE_CONFIGURATION
            self.config_root = config_root or self.DEFAULT_CONFIG_ROOT
            self._cache_runtime_filepaths()
            self.__setup_node_storage(node_storage=node_storage)

        # Network
        self.controller_port = controller_port or self.DEFAULT_CONTROLLER_PORT
        self.network_middleware = network_middleware or self.DEFAULT_NETWORK_MIDDLEWARE(registry=self.registry)
        self.interface_signature = interface_signature

        super().__init__(filepath=self.config_file_location, config_root=self.config_root)

    def __call__(self, **character_kwargs):
        return self.produce(**character_kwargs)

    def update(self, **kwargs) -> None:
        """
        A facility for updating existing attributes on existing configuration instances.

        Warning: This method allows mutation and may result in an inconsistent configuration.
        """
        return super().update(modifier=self.checksum_address, filepath=self.config_file_location, **kwargs)

    @classmethod
    def generate(cls, password: str, *args, **kwargs):
        """Shortcut: Hook-up a new initial installation and write configuration file to the disk"""
        node_config = cls(dev_mode=False, *args, **kwargs)
        node_config.initialize(password=password)
        node_config.to_configuration_file()
        return node_config

    def cleanup(self) -> None:
        if self.__dev_mode:
            self.__temp_dir.cleanup()

    @property
    def dev_mode(self) -> bool:
        return self.__dev_mode

    def __setup_node_storage(self, node_storage=None) -> None:
        if self.dev_mode:
            node_storage = ForgetfulNodeStorage(registry=self.registry, federated_only=self.federated_only)
        elif not node_storage:
            node_storage = LocalFileBasedNodeStorage(registry=self.registry,
                                                     config_root=self.config_root,
                                                     federated_only=self.federated_only)
        self.node_storage = node_storage

    def forget_nodes(self) -> None:
        self.node_storage.clear()
        message = "Removed all stored node node metadata and certificates"
        self.log.debug(message)

    def destroy(self) -> None:
        """Parse a node configuration and remove all associated files from the filesystem"""
        self.attach_keyring()
        self.keyring.destroy()
        os.remove(self.config_file_location)

    def generate_parameters(self, **overrides) -> dict:
        """
        Warning: This method allows mutation and may result in an inconsistent configuration.
        """
        merged_parameters = {**self.static_payload(), **self.dynamic_payload, **overrides}
        non_init_params = ('config_root',
                           'poa',
                           'light',
                           'provider_uri',
                           'registry_filepath',
                           'gas_strategy',
                           'signer_uri')
        character_init_params = filter(lambda t: t[0] not in non_init_params, merged_parameters.items())
        return dict(character_init_params)

    def produce(self, **overrides) -> CHARACTER_CLASS:
        """Initialize a new character instance and return it."""
        merged_parameters = self.generate_parameters(**overrides)
        character = self.CHARACTER_CLASS(**merged_parameters)
        return character

    @classmethod
    def assemble(cls, filepath: str = None, **overrides) -> dict:
        """
        Warning: This method allows mutation and may result in an inconsistent configuration.
        """
        payload = cls._read_configuration_file(filepath=filepath)
        node_storage = cls.load_node_storage(storage_payload=payload['node_storage'],
                                             federated_only=payload['federated_only'])
        domains = set(payload['domains'])

        # Assemble
        payload.update(dict(node_storage=node_storage, domains=domains))
        # Filter out None values from **overrides to detect, well, overrides...
        # Acts as a shim for optional CLI flags.
        overrides = {k: v for k, v in overrides.items() if v is not None}
        payload = {**payload, **overrides}
        return payload

    @classmethod
    def from_configuration_file(cls,
                                filepath: str = None,
                                provider_process=None,
                                **overrides  # < ---- Inlet for CLI Flags
                                ) -> 'CharacterConfiguration':
        """Initialize a CharacterConfiguration from a JSON file."""
        filepath = filepath or cls.default_filepath()
        assembled_params = cls.assemble(filepath=filepath, **overrides)
        try:
            node_configuration = cls(filepath=filepath, provider_process=provider_process, **assembled_params)
        except TypeError as e:
            raise cls.ConfigurationError(e)
        return node_configuration

    def validate(self) -> bool:

        # Top-level
        if not os.path.exists(self.config_root):
            raise self.ConfigurationError(f'No configuration directory found at {self.config_root}.')

        # Sub-paths
        filepaths = self.runtime_filepaths
        for field, path in filepaths.items():
            if path and not os.path.exists(path):
                message = 'Missing configuration file or directory: {}.'
                if 'registry' in path:
                    message += ' Did you mean to pass --federated-only?'
                raise CharacterConfiguration.InvalidConfiguration(message.format(path))
        return True

    def static_payload(self) -> dict:
        """Exported static configuration values for initializing Ursula"""

        payload = dict(

            # Identity
            federated_only=self.federated_only,
            checksum_address=self.checksum_address,
            keyring_root=self.keyring_root,

            # Behavior
            domains=list(self.domains),  # From Set
            learn_on_same_thread=self.learn_on_same_thread,
            abort_on_learning_error=self.abort_on_learning_error,
            start_learning_now=self.start_learning_now,
            save_metadata=self.save_metadata,
            node_storage=self.node_storage.payload(),
        )

        # Optional values (mode)
        if not self.federated_only:
            if self.provider_uri:
                if not self.signer_uri:
                    self.signer_uri = self.provider_uri
                payload.update(dict(provider_uri=self.provider_uri,
                                    poa=self.poa,
                                    light=self.is_light,
                                    signer_uri=self.signer_uri))
            if self.registry_filepath:
                payload.update(dict(registry_filepath=self.registry_filepath))

            # Gas Price
            payload.update(dict(gas_strategy=self.gas_strategy))

        # Merge with base payload
        base_payload = super().static_payload()
        base_payload.update(payload)

        return payload

    @property  # TODO: Graduate to a method and "derive" dynamic from static payload.
    def dynamic_payload(self) -> dict:
        """Exported dynamic configuration values for initializing Ursula"""
        payload = dict()
        if not self.federated_only:
            payload.update(dict(registry=self.registry, signer=Signer.from_signer_uri(self.signer_uri)))

        payload.update(dict(network_middleware=self.network_middleware or self.DEFAULT_NETWORK_MIDDLEWARE(),
                            known_nodes=self.known_nodes,
                            node_storage=self.node_storage,
                            crypto_power_ups=self.derive_node_power_ups()))
        return payload

    def generate_filepath(self, filepath: str = None, modifier: str = None, override: bool = False) -> str:
        modifier = modifier or self.checksum_address
        filepath = super().generate_filepath(filepath=filepath, modifier=modifier, override=override)
        return filepath

    @property
    def runtime_filepaths(self) -> dict:
        filepaths = dict(config_root=self.config_root,
                         keyring_root=self.keyring_root,
                         registry_filepath=self.registry_filepath)
        return filepaths

    @classmethod
    def generate_runtime_filepaths(cls, config_root: str) -> dict:
        """Dynamically generate paths based on configuration root directory"""
        filepaths = dict(config_root=config_root,
                         config_file_location=os.path.join(config_root, cls.generate_filename()),
                         keyring_root=os.path.join(config_root, 'keyring'))
        return filepaths

    def _cache_runtime_filepaths(self) -> None:
        """Generate runtime filepaths and cache them on the config object"""
        filepaths = self.generate_runtime_filepaths(config_root=self.config_root)
        for field, filepath in filepaths.items():
            if getattr(self, field) is UNINITIALIZED_CONFIGURATION:
                setattr(self, field, filepath)

    def attach_keyring(self, checksum_address: str = None, *args, **kwargs) -> None:
        account = checksum_address or self.checksum_address
        if not account:
            raise self.ConfigurationError("No account specified to unlock keyring")
        if self.keyring is not NO_KEYRING_ATTACHED:
            if self.keyring.checksum_address != account:
                raise self.ConfigurationError("There is already a keyring attached to this configuration.")
            return
        self.keyring = NucypherKeyring(keyring_root=self.keyring_root, account=account, *args, **kwargs)

    def derive_node_power_ups(self) -> List[CryptoPowerUp]:
        power_ups = list()
        if self.is_me and not self.dev_mode:
            for power_class in self.CHARACTER_CLASS._default_crypto_powerups:
                power_up = self.keyring.derive_crypto_power(power_class)
                power_ups.append(power_up)
        return power_ups

    def initialize(self, password: str) -> str:
        """Initialize a new configuration and write installation files to disk."""

        # Development
        if self.dev_mode:
            self.__temp_dir = TemporaryDirectory(prefix=self.TEMP_CONFIGURATION_DIR_PREFIX)
            self.config_root = self.__temp_dir.name

        # Persistent
        else:
            self._ensure_config_root_exists()
            self.write_keyring(password=password)

        self._cache_runtime_filepaths()
        self.node_storage.initialize()

        # Validate
        if not self.__dev_mode:
            self.validate()

        # Success
        message = "Created nucypher installation files at {}".format(self.config_root)
        self.log.debug(message)
        return self.config_root

    def write_keyring(self, password: str, checksum_address: str = None, **generation_kwargs) -> NucypherKeyring:

        if self.federated_only:
            checksum_address = FEDERATED_ADDRESS

        elif not checksum_address:

            # Note: It is assumed the blockchain interface is not yet connected.
            if self.provider_process:

                # Generate Geth's "datadir"
                if not os.path.exists(self.provider_process.data_dir):
                    os.mkdir(self.provider_process.data_dir)

                # Get or create wallet address
                if not self.checksum_address:
                    self.checksum_address = self.provider_process.ensure_account_exists(password=password)
                elif self.checksum_address not in self.provider_process.accounts():
                    raise self.ConfigurationError(f'Unknown Account {self.checksum_address}')

            elif not self.checksum_address:
                raise self.ConfigurationError(f'No checksum address provided for decentralized configuration.')

            checksum_address = self.checksum_address

        self.keyring = NucypherKeyring.generate(password=password,
                                                keyring_root=self.keyring_root,
                                                checksum_address=checksum_address,
                                                **generation_kwargs)

        if self.federated_only:
            self.checksum_address = self.keyring.checksum_address

        return self.keyring

    @classmethod
    def load_node_storage(cls, storage_payload: dict, federated_only: bool):
        from nucypher.config.storages import NodeStorage
        node_storage_subclasses = {storage._name: storage for storage in NodeStorage.__subclasses__()}
        storage_type = storage_payload[NodeStorage._TYPE_LABEL]
        storage_class = node_storage_subclasses[storage_type]
        node_storage = storage_class.from_payload(payload=storage_payload, federated_only=federated_only)
        return node_storage
