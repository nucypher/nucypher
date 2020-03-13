import json
import os
from abc import ABC, abstractmethod
from typing import Union

from constant_sorrow.constants import (
    UNKNOWN_VERSION
)

from nucypher.config import constants


class BaseConfiguration(ABC):
    """
    Abstract base class for saving a JSON serializable version of the subclass's attributes
    to the disk exported by `static_payload`, generating an optionally unique filename,
    and restoring a subclass instance from the written JSON file by passing the deserialized
    values to the subclass's constructor.

    Implementation
    ==============

    `_NAME` and `def static_payload` are required for subclasses, for example:


        ```
        class MyItem(BaseConfiguration):
            _NAME = 'my-item'

        ```
        AND

        ```
        def static_payload(self) -> dict:
            payload = dict(**super().static_payload(), key=value)
            return payload
        ```

        OR

        ```
        def static_payload(self) -> dict:
            subclass_payload = {'key': 'value'}
            payload = {**super().static_payload(), **subclass_payload}
            return payload
        ```

    Filepath Generation
    ===================

    Default behavior *avoids* overwriting an existing configuration file:

    - The name of the JSON file to write/read from is determined by `_NAME`.
      When calling `to_configuration_file`.

    - If the default path (i.e. `my-item.json`) already  exists and, optionally,
      `override` is set to `False`, then a `modifer` is appended to the name (i.e. `my-item-<MODIFIER>.json`).

    - If `modifier` is `None` and override is `False`, `FileExistsError` will be raised.

    If the subclass implementation has a global unique identifier, an additional method override
    to `to_configuration_file` will automate the renaming process.

        ```
        def to_configuration_file(*args, **kwargs) -> str:
            filepath = super().to_configuration_file(modifier=<MODIFIER>, *args, **kwargs)
            return filepath
        ```

    """

    _NAME = NotImplemented
    _CONFIG_FILE_EXTENSION = 'json'

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
        pass

    def __init__(self,
                 config_root: str = None,
                 filepath: str = None,
                 *args, **kwargs):

        if self._NAME is NotImplemented:
            error = f'_NAME must be implemented on BaseConfiguration subclass {self.__class__.__name__}'
            raise TypeError(error)

        self.config_root = config_root or self.DEFAULT_CONFIG_ROOT
        if not filepath:
            filepath = os.path.join(self.config_root, self.generate_filename())
        self.filepath = filepath

        super().__init__()

    def __eq__(self, other):
        return bool(self.static_payload() == other.static_payload())

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
        name = cls._NAME.lower()
        if modifier:
            name += f'-{modifier}'
        filename = f'{name}.{cls._CONFIG_FILE_EXTENSION.lower()}'
        return filename

    @classmethod
    def default_filepath(cls, config_root: str = None) -> str:
        """
        Generates the default configuration filepath for the class.

        :return: The generated filepath string
        """
        filename = cls.generate_filename()
        default_path = os.path.join(config_root or cls.DEFAULT_CONFIG_ROOT, filename)
        return default_path

    def generate_filepath(self, filepath: str = None, modifier: str = None, override: bool = False) -> str:
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
            filepath = os.path.join(self.config_root, filename)
        if os.path.exists(filepath) and not override:
            if not modifier:
                raise FileExistsError(f"{filepath} exists and no filename modifier supplied.")
            filename = self.generate_filename(modifier=modifier)
            filepath = os.path.join(self.config_root, filename)
        self.filepath = filepath
        return filepath

    def _ensure_config_root_exists(self) -> None:
        """
        Before writing to a configuration file, ensures that
        self.config_root exists on the filesystem.

        :return: None.
        """
        if not os.path.exists(self.config_root):
            try:
                os.mkdir(self.config_root, mode=0o755)
            except FileNotFoundError:
                os.makedirs(self.config_root, mode=0o755)

    @classmethod
    def peek(cls, filepath: str, field: str) -> Union[str, None]:
        payload = cls._read_configuration_file(filepath=filepath)
        try:
            result = payload[field]
        except KeyError:
            raise cls.ConfigurationError(f"Cannot peek; No such configuration field '{field}', options are {list(payload.keys())}")
        return result

    def to_configuration_file(self, filepath: str = None, modifier: str = None, override: bool = False) -> str:
        filepath = self.generate_filepath(filepath=filepath, modifier=modifier, override=override)
        self._ensure_config_root_exists()
        filepath = self._write_configuration_file(filepath=filepath, override=override)
        return filepath

    @classmethod
    def from_configuration_file(cls, filepath: str = None, **overrides) -> 'BaseConfiguration':
        filepath = filepath or cls.default_filepath()
        payload = cls._read_configuration_file(filepath=filepath)
        instance = cls(filepath=filepath, **payload, **overrides)
        return instance

    @classmethod
    def _read_configuration_file(cls, filepath: str) -> dict:
        """Reads `filepath` and returns the deserialized JSON payload dict."""
        with open(filepath, 'r') as file:
            raw_contents = file.read()
            payload = cls.deserialize(raw_contents)
        return payload

    def _write_configuration_file(self, filepath: str, override: bool = False) -> str:
        """Writes to `filepath` and returns the written filepath.  Raises `FileExistsError` if the file exists."""
        if os.path.exists(filepath) and not override:
            raise FileExistsError(f"{filepath} exists and no filename modifier supplied.")
        with open(filepath, 'w') as file:
            file.write(self.serialize())
        return filepath

    def serialize(self, serializer=json.dumps) -> str:
        """Returns the JSON serialized output of `static_payload`"""
        payload = self.static_payload()
        payload['version'] = self.VERSION
        serialized_payload = serializer(payload, indent=self.INDENTATION)
        return serialized_payload

    @classmethod
    def deserialize(cls, payload: str, deserializer=json.loads) -> dict:
        """Returns the JSON deserialized content of `payload`"""
        deserialized_payload = deserializer(payload)
        version = deserialized_payload.pop('version', UNKNOWN_VERSION)
        if version != cls.VERSION:
            raise cls.OldVersion(f"Configuration file is the wrong version "
                                 f"Expected version {cls.VERSION}; Got version {version}")
        return deserialized_payload

    def update(self, filepath: str = None, modifier: str = None, **updates):
        for field, value in updates.items():
            try:
                getattr(self, field)
            except AttributeError:
                raise self.ConfigurationError(f"Cannot update '{field}'. It is an invalid configuration field.")
            else:
                setattr(self, field, value)
        self.to_configuration_file(filepath=filepath, modifier=modifier, override=True)
