import json
import os
from abc import ABC, abstractmethod

from nucypher.config import constants


class BaseConfiguration(ABC):

    _NAME = NotImplemented
    _CONFIG_FILE_EXTENSION = 'json'

    DEFAULT_CONFIG_ROOT = constants.DEFAULT_CONFIG_ROOT

    class ConfigurationError(RuntimeError):
        pass

    class InvalidConfiguration(ConfigurationError):
        pass

    class NoConfigurationRoot(InvalidConfiguration):
        pass

    def __init__(self,
                 config_root: str = None,
                 filepath: str = None,
                 *args, **kwargs):

        self.config_root = config_root or self.DEFAULT_CONFIG_ROOT
        self.filepath = filepath or self.default_filepath()
        super().__init__()

    def __eq__(self, other):
        return bool(self.static_payload() == other.static_payload())

    @abstractmethod
    def static_payload(self) -> dict:
        raise NotImplementedError

    @classmethod
    def generate_filename(cls, modifier: str = None) -> str:
        name = cls._NAME.lower()
        if modifier:
            name += f'-{modifier}'
        filename = f'{name}.{cls._CONFIG_FILE_EXTENSION.lower()}'
        return filename

    @classmethod
    def default_filepath(cls):
        filename = cls.generate_filename()
        default_path = os.path.join(cls.DEFAULT_CONFIG_ROOT, filename)
        return default_path

    def generate_filepath(self, filepath: str = None, modifier: str = None, override: bool = False) -> str:
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

    def to_configuration_file(self, filepath: str = None, modifier: str = None, override: bool = False) -> str:
        filepath = self.generate_filepath(filepath=filepath, modifier=modifier, override=override)
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
        try:
            with open(filepath, 'r') as file:
                raw_contents = file.read()
                payload = cls.deserialize(raw_contents)
        except FileNotFoundError:
            raise
        return payload

    def _write_configuration_file(self, filepath: str, override: bool = False) -> str:
        if os.path.exists(filepath) and not override:
            raise FileExistsError
        try:
            with open(filepath, 'w') as file:
                file.write(self.serialize())
        except FileNotFoundError:
            raise
        return filepath

    def serialize(self, serializer=json.dumps):
        try:
            serialized_payload = serializer(self.static_payload(), indent=4)
        except json.JSONDecodeError:
            raise
        return serialized_payload

    @classmethod
    def deserialize(cls, payload: str, deserializer=json.loads) -> dict:
        try:
            deserialized_payload = deserializer(payload)
        except json.JSONDecodeError:
            raise
        return deserialized_payload
