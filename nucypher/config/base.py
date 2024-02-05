import json
import re
from abc import ABC, abstractmethod
from decimal import Decimal
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Callable, List, Optional, Union

from constant_sorrow.constants import (
    DEVELOPMENT_CONFIGURATION,
    LIVE_CONFIGURATION,
    NO_BLOCKCHAIN_CONNECTION,
    NO_KEYSTORE_ATTACHED,
    UNINITIALIZED_CONFIGURATION,
    UNKNOWN_VERSION,
)
from eth_utils.address import is_checksum_address

from nucypher.blockchain.eth import domains
from nucypher.blockchain.eth.interfaces import BlockchainInterfaceFactory
from nucypher.blockchain.eth.registry import (
    ContractRegistry,
    LocalRegistrySource,
)
from nucypher.blockchain.eth.signers import Signer
from nucypher.characters.lawful import Ursula
from nucypher.config import constants
from nucypher.config.util import cast_paths_from
from nucypher.crypto.keystore import Keystore
from nucypher.crypto.powers import CryptoPower, CryptoPowerUp
from nucypher.network.middleware import RestMiddleware
from nucypher.policy.payment import PRE_PAYMENT_METHODS
from nucypher.utilities.logging import Logger


class BaseConfiguration(ABC):
    """
    Abstract base class for saving a JSON serializable version of the subclass's attributes
    to the disk exported by `static_payload`, generating an optionally unique filename,
    and restoring a subclass instance from the written JSON file by passing the deserialized
    values to the subclass's constructor.

    Implementation:

    `NAME` and `def static_payload` are required for subclasses, for example:

    .. code::

        class MyItem(BaseConfiguration):
            _NAME = 'my-item'

    AND

    .. code::

        def static_payload(self) -> dict:
            payload = dict(**super().static_payload(), key=value)
            return payload

    OR

    .. code::

        def static_payload(self) -> dict:
            subclass_payload = {'key': 'value'}
            payload = {**super().static_payload(), **subclass_payload}
            return payload

    Filepath Generation

    Default behavior *avoids* overwriting an existing configuration file:

    - The name of the JSON file to write/read from is determined by `NAME`.
      When calling `to_configuration_file`.

    - If the default path (i.e. `my-item.json`) already  exists and, optionally,
      `override` is set to `False`, then a `modifer` is appended to the name (i.e. `my-item-<MODIFIER>.json`).

    - If `modifier` is `None` and override is `False`, `FileExistsError` will be raised.

    If the subclass implementation has a global unique identifier, an additional method override
    to `to_configuration_file` will automate the renaming process.

    .. code::

        def to_configuration_file(*args, **kwargs) -> str:
            filepath = super().to_configuration_file(modifier=<MODIFIER>, *args, **kwargs)
            return filepath
    """

    NAME = NotImplemented
    _CONFIG_FILE_EXTENSION = "json"

    INDENTATION = 2
    DEFAULT_CONFIG_ROOT = constants.DEFAULT_CONFIG_ROOT

    VERSION = NotImplemented

    class ConfigurationError(RuntimeError):
        pass

    class InvalidConfiguration(ConfigurationError):
        pass

    class NoConfigurationRoot(InvalidConfiguration):
        pass

    class OldVersion(InvalidConfiguration):
        def __init__(self, version: int, *args, **kwargs):
            self.version = version
            super().__init__(*args, *kwargs)

    def __init__(
        self,
        config_root: Optional[Path] = None,
        filepath: Optional[Path] = None,
        *args,
        **kwargs,
    ):
        if self.NAME is NotImplemented:
            error = f"NAME must be implemented on BaseConfiguration subclass {self.__class__.__name__}"
            raise TypeError(error)

        self.config_root = config_root or self.DEFAULT_CONFIG_ROOT
        if not filepath:
            filepath = self.config_root / self.generate_filename()
        self.filepath = filepath

        super().__init__()

    @abstractmethod
    def static_payload(self) -> dict:
        """
        Return a dictionary of JSON serializable configuration key/value pairs
        matching the input specification of this classes __init__.

        Recommended subclass implementations:

        ```
        payload = dict(**super().static_payload(), key=value)
        return payload
        ```

        OR

        ```
        subclass_payload = {'key': 'value'}
        payload = {**super().static_payload(), **subclass_payload}
        return payload
        ```

        """
        payload = dict(config_root=self.config_root)
        return payload

    @classmethod
    def generate_filename(cls, modifier: str = None) -> str:
        """
        Generates the configuration filename with an optional modification string.

        :param modifier: String to modify default filename with.
        :return: The generated filepath string.
        """
        name = cls.NAME.lower()
        if modifier:
            name += f"-{modifier}"
        filename = f"{name}.{cls._CONFIG_FILE_EXTENSION.lower()}"
        return filename

    @classmethod
    def default_filepath(cls, config_root: Optional[Path] = None) -> Path:
        """
        Generates the default configuration filepath for the class.

        :return: The generated filepath string
        """
        filename = cls.generate_filename()
        default_path = (config_root or cls.DEFAULT_CONFIG_ROOT) / filename
        return default_path

    def generate_filepath(
        self,
        filepath: Optional[Path] = None,
        modifier: str = None,
        override: bool = False,
    ) -> Path:
        """
        Generates a filepath for saving to writing to a configuration file.

        Default behavior *avoids* overwriting an existing configuration file:

        - The filepath exists and a filename `modifier` is not provided, then `FileExistsError` will be raised.
        - The modified filepath exists, then `FileExistsError` will be raised.

        To allow re-generation of an existing filepath, set `override` to True.

        :param filepath: A custom filepath to use for configuration.
        :param modifier: A unique string to modify the filename if the file already exists.
        :param override: Allow generation of an existing filepath.
        :return: The generated filepath.

        """
        if not filepath:
            filename = self.generate_filename()
            filepath = self.config_root / filename
        if filepath.exists() and not override:
            if not modifier:
                raise FileExistsError(
                    f"{filepath} exists and no filename modifier supplied."
                )
            filename = self.generate_filename(modifier=modifier)
            filepath = self.config_root / filename
        self.filepath = filepath
        return filepath

    def _ensure_config_root_exists(self) -> None:
        """
        Before writing to a configuration file, ensures that
        self.config_root exists on the filesystem.

        :return: None.
        """
        if not self.config_root.exists():
            try:
                self.config_root.mkdir(mode=0o755)
            except FileNotFoundError:
                self.config_root.mkdir(parents=True, mode=0o755)

    @classmethod
    def peek(cls, filepath: Path, field: str) -> Union[str, None]:
        payload = cls._read_configuration_file(filepath=filepath)
        try:
            result = payload[field]
        except KeyError:
            raise cls.ConfigurationError(
                f"Cannot peek; No such configuration field '{field}', options are {list(payload.keys())}"
            )
        return result

    def to_configuration_file(
        self,
        filepath: Optional[Path] = None,
        modifier: str = None,
        override: bool = False,
    ) -> Path:
        filepath = self.generate_filepath(
            filepath=filepath, modifier=modifier, override=override
        )
        self._ensure_config_root_exists()
        filepath = self._write_configuration_file(filepath=filepath, override=override)
        return filepath

    @classmethod
    def from_configuration_file(
        cls, filepath: Optional[Path] = None, **overrides
    ) -> "BaseConfiguration":
        filepath = filepath or cls.default_filepath()
        payload = cls._read_configuration_file(filepath=filepath)
        instance = cls(filepath=filepath, **payload, **overrides)
        return instance

    @classmethod
    def _read_configuration_file(cls, filepath: Path) -> dict:
        """Reads `filepath` and returns the deserialized JSON payload dict."""
        with open(filepath, "r") as file:
            raw_contents = file.read()
            payload = cls.deserialize(raw_contents, payload_label=str(filepath))
        return payload

    def _write_configuration_file(self, filepath: Path, override: bool = False) -> Path:
        """Writes to `filepath` and returns the written filepath.  Raises `FileExistsError` if the file exists."""
        if filepath.exists() and not override:
            raise FileExistsError(
                f"{filepath} exists and no filename modifier supplied."
            )
        with open(filepath, "w") as file:
            file.write(self.serialize())
        return filepath

    def serialize(self, serializer=json.dumps) -> str:
        """Returns the JSON serialized output of `static_payload`"""

        def _stringify_paths(d: dict):
            for key, value in d.items():
                if isinstance(value, Path):
                    d[key] = str(value)
                if isinstance(value, dict):
                    _stringify_paths(value)

        payload = self.static_payload()
        _stringify_paths(payload)
        payload["version"] = self.VERSION
        serialized_payload = serializer(payload, indent=self.INDENTATION)
        return serialized_payload

    @classmethod
    def deserialize(
        cls, payload: str, deserializer=json.loads, payload_label: Optional[str] = None
    ) -> dict:
        """Returns the JSON deserialized content of `payload`"""
        deserialized_payload = deserializer(payload)
        version = deserialized_payload.pop("version", UNKNOWN_VERSION)
        if version != cls.VERSION:
            label = f"'{payload_label}' " if payload_label else ""
            raise cls.OldVersion(
                version,
                f"Configuration {label} is the wrong version "
                f"Expected version {cls.VERSION}; Got version {version}",
            )

        deserialized_payload = cast_paths_from(cls, deserialized_payload)
        return deserialized_payload

    def update(self, filepath: Optional[Path] = None, **updates) -> None:
        for field, value in updates.items():
            try:
                getattr(self, field)
            except AttributeError:
                raise self.ConfigurationError(
                    f"Cannot update '{field}'. It is an invalid configuration field."
                )
            else:
                setattr(self, field, value)
        # just write the configuration file, file exists and we are overriding
        self._write_configuration_file(filepath=filepath, override=True)


class CharacterConfiguration(BaseConfiguration):
    """
    'Sideways Engagement' of Character classes; a reflection of input parameters.
    """

    VERSION = 9  # bump when static payload scheme changes

    CHARACTER_CLASS = NotImplemented
    MNEMONIC_KEYSTORE = False
    DEFAULT_DOMAIN = domains.DEFAULT_DOMAIN
    DEFAULT_NETWORK_MIDDLEWARE = RestMiddleware
    TEMP_CONFIGURATION_DIR_PREFIX = "tmp-nucypher"
    SIGNER_ENVVAR = None

    # When we begin to support other threshold schemes,
    # this will be one of the concepts that makes us want a factory.  #571
    known_node_class = Ursula

    # Gas
    DEFAULT_GAS_STRATEGY = "fast"

    # Payments
    DEFAULT_PRE_PAYMENT_METHOD = "SubscriptionManager"

    # Fields specified here are *not* passed into the Character's constructor
    # and can be understood as configuration fields only.
    _CONFIG_FIELDS = (
        "config_root",
        "poa",
        "light",
        "registry_filepath",
        "gas_strategy",
        "max_gas_price",  # gwei
        "signer_uri",
        "keystore_path",
    )

    def __init__(
        self,
        # Base
        emitter=None,
        config_root: Optional[Path] = None,
        filepath: Optional[Path] = None,
        # Mode
        dev_mode: bool = False,
        # Identity
        checksum_address: Optional[str] = None,
        crypto_power: Optional[CryptoPower] = None,
        # Keystore
        keystore: Optional[Keystore] = None,
        keystore_path: Optional[Path] = None,
        # Learner
        learn_on_same_thread: bool = False,
        abort_on_learning_error: bool = False,
        start_learning_now: bool = True,
        # Network
        domain: str = DEFAULT_DOMAIN,
        network_middleware: Optional[RestMiddleware] = None,
        lonely: bool = False,
        # Node Storage
        known_nodes: Optional[set] = None,
        reload_metadata: bool = True,
        save_metadata: bool = True,
        # Blockchain
        poa: Optional[bool] = None,
        light: bool = False,
        eth_endpoint: Optional[str] = None,
        polygon_endpoint: Optional[str] = None,
        gas_strategy: Union[Callable, str] = DEFAULT_GAS_STRATEGY,
        max_gas_price: Optional[int] = None,
        signer_uri: Optional[str] = None,
        # Payments
        # TODO: Resolve code prefixing below, possibly with the use of nested configuration fields
        pre_payment_method: Optional[str] = None,
        # Registries
        registry: Optional[ContractRegistry] = None,
        registry_filepath: Optional[Path] = None,
    ):
        self.emitter = emitter

        self.log = Logger(self.__class__.__name__)

        # This constant is used to signal that a path can be generated if one is not provided.
        UNINITIALIZED_CONFIGURATION.bool_value(False)

        # Identity
        # NOTE: NodeConfigurations can only be used with Self-Characters
        self.is_me = True
        self.checksum_address = checksum_address

        # Keystore
        self.crypto_power = crypto_power
        if keystore_path and not keystore:
            keystore = Keystore(keystore_path=keystore_path)
        self.__keystore = self.__keystore = keystore or NO_KEYSTORE_ATTACHED.bool_value(
            False
        )
        self.keystore_dir = (
            Path(keystore.keystore_path).parent
            if keystore
            else UNINITIALIZED_CONFIGURATION
        )

        # Contract Registry
        if registry and registry_filepath:
            if registry.filepath != registry_filepath:
                error = (
                    f"Inconsistent registry filepaths for '{registry.filepath.absolute()}'"
                    f" and '{registry_filepath.absolute()}'."
                )
                raise ValueError(error)
            else:
                self.log.warn("Registry and registry filepath were both passed.")
        self.registry = registry or NO_BLOCKCHAIN_CONNECTION.bool_value(False)
        self.registry_filepath = registry_filepath or UNINITIALIZED_CONFIGURATION

        # Blockchain
        self.poa = poa
        self.is_light = light
        self.eth_endpoint = eth_endpoint or NO_BLOCKCHAIN_CONNECTION
        self.polygon_endpoint = polygon_endpoint or NO_BLOCKCHAIN_CONNECTION
        self.signer_uri = signer_uri or None

        # Learner
        self.domain = domains.get_domain(str(domain))
        self.learn_on_same_thread = learn_on_same_thread
        self.abort_on_learning_error = abort_on_learning_error
        self.start_learning_now = start_learning_now
        self.save_metadata = save_metadata
        self.reload_metadata = reload_metadata
        self.known_nodes = known_nodes or set()  # handpicked
        self.lonely = lonely

        # Configuration
        self.__dev_mode = dev_mode
        self.config_file_location = filepath or UNINITIALIZED_CONFIGURATION
        self.config_root = UNINITIALIZED_CONFIGURATION

        #
        # Decentralized
        #

        self.gas_strategy = gas_strategy
        self.max_gas_price = max_gas_price  # gwei

        if not self.registry:
            if not self.registry_filepath:
                self.log.info("Fetching latest registry from source.")
                self.registry = ContractRegistry.from_latest_publication(
                    domain=self.domain
                )
            else:
                source = LocalRegistrySource(
                    domain=self.domain, filepath=self.registry_filepath
                )
                self.registry = ContractRegistry(source=source)
                self.log.info(f"Using local registry ({self.registry}).")

        self.signer = Signer.from_signer_uri(
            self.signer_uri, testnet=self.domain.is_testnet
        )

        #
        # Onchain Payments & Policies
        #

        # FIXME: Enforce this for Ursula/Alice but not Bob?
        from nucypher.config.characters import BobConfiguration

        if not isinstance(self, BobConfiguration):
            self.pre_payment_method = (
                pre_payment_method or self.DEFAULT_PRE_PAYMENT_METHOD
            )

        if dev_mode:
            self.__temp_dir = UNINITIALIZED_CONFIGURATION
            self.initialize(password=DEVELOPMENT_CONFIGURATION)
        else:
            self.__temp_dir = LIVE_CONFIGURATION
            self.config_root = config_root or self.DEFAULT_CONFIG_ROOT
            self._cache_runtime_filepaths()

        # Network
        self.network_middleware = network_middleware or self.DEFAULT_NETWORK_MIDDLEWARE(
            registry=self.registry, eth_endpoint=self.eth_endpoint
        )

        super().__init__(
            filepath=self.config_file_location, config_root=self.config_root
        )

    def _connect_to_endpoints(self, endpoints: List[str]) -> None:
        for endpoint in endpoints:
            if endpoint and endpoint != NO_BLOCKCHAIN_CONNECTION:
                is_initialized = BlockchainInterfaceFactory.is_interface_initialized(
                    endpoint=endpoint
                )

                if not is_initialized:
                    BlockchainInterfaceFactory.initialize_interface(
                        endpoint=endpoint,
                        poa=self.poa,
                        light=self.is_light,
                        emitter=self.emitter,
                        gas_strategy=self.gas_strategy,
                        max_gas_price=self.max_gas_price,
                    )
                else:
                    self.log.warn(
                        f"Using existing blockchain interface connection ({endpoint})."
                    )

    def __call__(self, **character_kwargs):
        return self.produce(**character_kwargs)

    @property
    def keystore(self) -> Keystore:
        return self.__keystore

    def attach_keystore(self, keystore: Keystore) -> None:
        self.__keystore = keystore

    @classmethod
    def address_from_filepath(cls, filepath: Path) -> str:
        pattern = re.compile(
            r"""
                             (^\w+)-
                             (0x{1}           # Then, 0x the start of the string, exactly once
                             [0-9a-fA-F]{40}) # Followed by exactly 40 hex chars
                             """,
            re.VERBOSE,
        )

        filename = filepath.name
        match = pattern.match(filename)

        if match:
            character_name, checksum_address = match.groups()
        else:
            # Extract from default by "peeking" inside the configuration file.
            default_name = cls.generate_filename()
            if filename == default_name:
                checksum_address = cls.peek(filepath=filepath, field="checksum_address")
            else:
                raise ValueError(f"Cannot extract checksum from filepath '{filepath}'")

        if not is_checksum_address(checksum_address):
            raise RuntimeError(
                f"Invalid checksum address detected in configuration file at '{filepath}'."
            )
        return checksum_address

    def update(self, **kwargs) -> None:
        """
        A facility for updating existing attributes on existing configuration instances.

        Warning: This method allows mutation and may result in an inconsistent configuration.
        """
        # config file should exist and we we override -> no need for modifier
        return super().update(filepath=self.config_file_location, **kwargs)

    @classmethod
    def generate(
        cls, password: str, key_material: Optional[bytes] = None, *args, **kwargs
    ):
        """Shortcut: Hook-up a new initial installation and configuration."""
        node_config = cls(dev_mode=False, *args, **kwargs)
        node_config.initialize(key_material=key_material, password=password)
        return node_config

    def cleanup(self) -> None:
        if self.__dev_mode:
            self.__temp_dir.cleanup()

    @property
    def dev_mode(self) -> bool:
        return self.__dev_mode

    def destroy(self) -> None:
        """Parse a node configuration and remove all associated files from the filesystem"""
        self.config_file_location.unlink()

    def generate_parameters(self, **overrides) -> dict:
        """
        Warning: This method allows mutation and may result in an inconsistent configuration.
        """
        merged_parameters = {
            **self.static_payload(),
            **self.dynamic_payload,
            **overrides,
        }
        character_init_params = filter(
            lambda t: t[0] not in self._CONFIG_FIELDS, merged_parameters.items()
        )
        return dict(character_init_params)

    def produce(self, **overrides) -> CHARACTER_CLASS:
        """Initialize a new character instance and return it."""
        # prime endpoint connections
        self._connect_to_endpoints(endpoints=[self.eth_endpoint, self.polygon_endpoint])

        merged_parameters = self.generate_parameters(**overrides)
        character = self.CHARACTER_CLASS(**merged_parameters)
        return character

    @classmethod
    def assemble(cls, filepath: Optional[Path] = None, **overrides) -> dict:
        """
        Warning: This method allows mutation and may result in an inconsistent configuration.
        """
        payload = cls._read_configuration_file(filepath=filepath)
        max_gas_price = payload.get("max_gas_price")  # gwei
        if max_gas_price:
            max_gas_price = Decimal(max_gas_price)

        # Assemble
        payload.update(dict(max_gas_price=max_gas_price))
        payload = cast_paths_from(cls, payload)

        # Filter out None values from **overrides to detect, well, overrides...
        # Acts as a shim for optional CLI flags.
        overrides = {k: v for k, v in overrides.items() if v is not None}
        payload = {**payload, **overrides}
        return payload

    @classmethod
    def from_configuration_file(
        cls, filepath: Optional[Path] = None, **overrides  # < ---- Inlet for CLI Flags
    ) -> "CharacterConfiguration":
        """Initialize a CharacterConfiguration from a JSON file."""
        filepath = filepath or cls.default_filepath()
        assembled_params = cls.assemble(filepath=filepath, **overrides)
        node_configuration = cls(filepath=filepath, **assembled_params)
        return node_configuration

    def validate(self) -> bool:
        # Top-level
        if not self.config_root.exists():
            raise self.ConfigurationError(
                f"No configuration directory found at {self.config_root}."
            )

        # Sub-paths
        filepaths = self.runtime_filepaths
        for field, path in filepaths.items():
            if path and not path.exists():
                message = "Missing configuration file or directory: {}."
                raise CharacterConfiguration.InvalidConfiguration(message.format(path))
        return True

    def static_payload(self) -> dict:
        """JSON-Exported static configuration values for initializing Ursula"""
        keystore_path = str(self.keystore.keystore_path) if self.keystore else None
        payload = dict(
            # Identity
            checksum_address=self.checksum_address,
            keystore_path=keystore_path,
            # Behavior
            domain=str(self.domain),
            learn_on_same_thread=self.learn_on_same_thread,
            abort_on_learning_error=self.abort_on_learning_error,
            start_learning_now=self.start_learning_now,
            save_metadata=self.save_metadata,
            lonely=self.lonely,
        )

        # Optional values (mode)
        if self.eth_endpoint:
            if not self.signer_uri:
                self.signer_uri = self.eth_endpoint
            payload.update(
                dict(
                    eth_endpoint=self.eth_endpoint,
                    poa=self.poa,
                    light=self.is_light,
                    signer_uri=self.signer_uri,
                )
            )
        if self.registry_filepath:
            payload.update(dict(registry_filepath=self.registry_filepath))

        if self.polygon_endpoint:
            payload.update(
                polygon_endpoint=self.polygon_endpoint,
            )

        # Gas Price
        __max_price = str(self.max_gas_price) if self.max_gas_price else None
        payload.update(dict(gas_strategy=self.gas_strategy, max_gas_price=__max_price))

        # Merge with base payload
        base_payload = super().static_payload()
        base_payload.update(payload)

        return payload

    @property
    def dynamic_payload(self) -> dict:
        """
        Exported dynamic configuration values for initializing Ursula.
        These values are used to init a character instance but are *not*
        saved to the JSON configuration.
        """
        payload = dict(
            registry=self.registry,
            signer=self.signer,
            network_middleware=self.network_middleware
            or self.DEFAULT_NETWORK_MIDDLEWARE(),
            known_nodes=self.known_nodes,
            keystore=self.keystore,
            crypto_power_ups=self.derive_node_power_ups(),
        )

        return payload

    def generate_filepath(
        self,
        filepath: Optional[Path] = None,
        modifier: str = None,
        override: bool = False,
    ) -> Path:
        modifier = modifier or self.checksum_address
        filepath = super().generate_filepath(
            filepath=filepath, modifier=modifier, override=override
        )
        return filepath

    @property
    def runtime_filepaths(self) -> dict:
        filepaths = dict(
            config_root=self.config_root,
            keystore_dir=self.keystore_dir,
            registry_filepath=self.registry_filepath,
        )
        return filepaths

    @classmethod
    def generate_runtime_filepaths(cls, config_root: Path) -> dict:
        """Dynamically generate paths based on configuration root directory"""
        filepaths = dict(
            config_root=config_root,
            config_file_location=config_root / cls.generate_filename(),
            keystore_dir=config_root / "keystore",
        )
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
            for power_class in self.CHARACTER_CLASS._default_crypto_powerups:
                power_up = self.keystore.derive_crypto_power(power_class)
                power_ups.append(power_up)
        return power_ups

    def initialize(self, password: str, key_material: Optional[bytes] = None) -> str:
        """Initialize a new configuration and write installation files to disk."""

        # Development
        if self.dev_mode:
            self.__temp_dir = TemporaryDirectory(
                prefix=self.TEMP_CONFIGURATION_DIR_PREFIX
            )
            self.config_root = Path(self.__temp_dir.name)

        # Persistent
        else:
            self._ensure_config_root_exists()
            self.write_keystore(
                key_material=key_material,
                password=password,
                interactive=self.MNEMONIC_KEYSTORE,
            )

        self._cache_runtime_filepaths()

        # Validate
        if not self.__dev_mode:
            self.validate()

        # Success
        message = "Created nucypher installation files at {}".format(self.config_root)
        self.log.debug(message)
        return Path(self.config_root)

    def write_keystore(
        self,
        password: str,
        key_material: Optional[bytes] = None,
        interactive: bool = True,
    ) -> Keystore:
        if key_material:
            self.__keystore = Keystore.import_secure(
                key_material=key_material,
                password=password,
                keystore_dir=self.keystore_dir,
            )
        else:
            if interactive:
                self.__keystore = Keystore.generate(
                    password=password,
                    keystore_dir=self.keystore_dir,
                    interactive=interactive,
                )
            else:
                self.__keystore, _ = Keystore.generate(
                    password=password,
                    keystore_dir=self.keystore_dir,
                    interactive=interactive,
                )

        return self.keystore

    def configure_pre_payment_method(self):
        # TODO: finalize config fields
        #
        # Strategy-Based (current implementation, inflexible & hardcoded)
        # 'pre_payment_strategy': 'SubscriptionManager'
        # 'network': 'polygon'
        # 'blockchain_endpoint': 'https:///polygon.infura.io....'
        #
        # Contract-Targeted (alternative implementation, flexible & generic)
        # 'pre_payment': {
        #     'contract': '0xdeadbeef'
        #     'abi': '/home/abi/sm.json'
        #     'function': 'isPolicyActive'
        #     'provider': 'https:///matic.infura.io....'
        # }
        #

        try:
            pre_payment_class = PRE_PAYMENT_METHODS[self.pre_payment_method]
        except KeyError:
            raise KeyError(f'Unknown PRE payment method "{self.pre_payment_method}"')

        if pre_payment_class.ONCHAIN:
            # on-chain payment strategies require a blockchain connection
            pre_payment_strategy = pre_payment_class(
                domain=self.domain,
                blockchain_endpoint=self.polygon_endpoint,
                registry=self.registry,
            )
        else:
            pre_payment_strategy = pre_payment_class()
        return pre_payment_strategy
