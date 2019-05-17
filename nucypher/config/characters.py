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
import datetime
import json
import os

from constant_sorrow.constants import (
    UNINITIALIZED_CONFIGURATION
)

from nucypher.config.constants import DEFAULT_CONFIG_ROOT
from nucypher.config.keyring import NucypherKeyring
from nucypher.config.node import NodeConfiguration


class UrsulaConfiguration(NodeConfiguration):
    from nucypher.characters.lawful import Ursula

    _CHARACTER_CLASS = Ursula
    _NAME = _CHARACTER_CLASS.__name__.lower()

    CONFIG_FILENAME = '{}.config'.format(_NAME)
    DEFAULT_CONFIG_FILE_LOCATION = os.path.join(DEFAULT_CONFIG_ROOT, CONFIG_FILENAME)
    DEFAULT_DB_NAME = '{}.db'.format(_NAME)

    def __init__(self,
                 dev_mode: bool = False,
                 db_filepath: str = None,
                 *args, **kwargs) -> None:
        self.db_filepath = db_filepath or UNINITIALIZED_CONFIGURATION
        super().__init__(dev_mode=dev_mode, *args, **kwargs)

    def generate_runtime_filepaths(self, config_root: str) -> dict:
        base_filepaths = super().generate_runtime_filepaths(config_root=config_root)
        filepaths = dict(db_filepath=os.path.join(config_root, self.DEFAULT_DB_NAME))
        base_filepaths.update(filepaths)
        return base_filepaths

    @property
    def static_payload(self) -> dict:
        payload = dict(
         rest_host=self.rest_host,
         rest_port=self.rest_port,
         db_filepath=self.db_filepath,
        )
        return {**super().static_payload, **payload}

    @property
    def dynamic_payload(self) -> dict:
        payload = dict(
            network_middleware=self.network_middleware,
            tls_curve=self.tls_curve,  # TODO: Needs to be in static payload with [str -> curve] mapping
            certificate=self.certificate,
            interface_signature=self.interface_signature,
            timestamp=None,
        )
        return {**super().dynamic_payload, **payload}

    def produce(self, **overrides):
        """Produce a new Ursula from configuration"""

        merged_parameters = self.generate_parameters(**overrides)
        ursula = self._CHARACTER_CLASS(**merged_parameters)

        if self.dev_mode:
            class MockDatastoreThreadPool(object):
                def callInThread(self, f, *args, **kwargs):
                    return f(*args, **kwargs)
            ursula.datastore_threadpool = MockDatastoreThreadPool()

        return ursula

    def write_keyring(self, password: str, **generation_kwargs) -> NucypherKeyring:

        return super().write_keyring(password=password,
                                     encrypting=True,
                                     rest=True,
                                     host=self.rest_host,
                                     curve=self.tls_curve,
                                     **generation_kwargs)

    def destroy(self) -> None:
        if os.path.isfile(self.db_filepath):
            os.remove(self.db_filepath)
        super().destroy()


class AliceConfiguration(NodeConfiguration):
    from nucypher.characters.lawful import Alice

    _CHARACTER_CLASS = Alice
    _NAME = _CHARACTER_CLASS.__name__.lower()

    CONFIG_FILENAME = '{}.config'.format(_NAME)
    DEFAULT_CONFIG_FILE_LOCATION = os.path.join(DEFAULT_CONFIG_ROOT, CONFIG_FILENAME)
    DEFAULT_REST_PORT = 8151

    DEFAULT_M = 2
    DEFAULT_N = 3
    DEFAULT_RATE = int(1e14)  # wei  # TODO: Best Sane Default
    DEFAULT_FIRST_PERIOD_RATE = DEFAULT_RATE * 0.25  # TODO:
    DEFAULT_EXPIRATION = datetime.timedelta(days=3)  # TODO:

    def __init__(self,
                 m: int = None,
                 n: int = None,
                 rate: int = None,
                 first_period_rate: float = None,
                 *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.m = m
        self.n = n
        self.rate = rate
        self.first_period_rate = first_period_rate

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
            filename = f'{self._NAME.lower()}{self._NAME.lower(), }'  # FIXME: Support multiple Alice configs
            filepath = os.path.join(self.config_root, filename)

        if os.path.isfile(filepath):
            # Avoid overriding an existing default configuration
            filename = f'{self._NAME.lower()}-{self.checksum_public_address[:6]}{self.__CONFIG_FILE_EXT}'
            filepath = os.path.join(self.config_root, filename)

        payload = self.static_payload
        del payload['is_me']

        # Serialize domains
        domains = list(str(domain) for domain in self.domains)

        # Save node connection data
        payload.update(dict(
            node_storage=self.node_storage.payload(),
            domains=domains,
            m=self.m,
            n=self.n,
            rate=self.rate,
            first_period_rate=self.first_period_rate
        ))

        with open(filepath, 'w') as config_file:
            config_file.write(json.dumps(payload, indent=4))
        return filepath

    def write_keyring(self, password: str, **generation_kwargs) -> NucypherKeyring:

        return super().write_keyring(password=password,
                                     encrypting=True,
                                     rest=False,
                                     **generation_kwargs)


class BobConfiguration(NodeConfiguration):
    from nucypher.characters.lawful import Bob

    _CHARACTER_CLASS = Bob
    _NAME = _CHARACTER_CLASS.__name__.lower()

    CONFIG_FILENAME = '{}.config'.format(_NAME)
    DEFAULT_CONFIG_FILE_LOCATION = os.path.join(DEFAULT_CONFIG_ROOT, CONFIG_FILENAME)
    DEFAULT_REST_PORT = 7151

    def write_keyring(self, password: str, **generation_kwargs) -> NucypherKeyring:

        return super().write_keyring(password=password,
                                     encrypting=True,
                                     rest=False,
                                     **generation_kwargs)


class FelixConfiguration(NodeConfiguration):
    from nucypher.characters.chaotic import Felix

    def __init__(self, db_filepath: str = None, *args, **kwargs) -> None:

        # Character
        super().__init__(*args, **kwargs)

        # Felix
        self.db_filepath = db_filepath or os.path.join(self.config_root, self.DEFAULT_DB_NAME)

    # Character
    _CHARACTER_CLASS = Felix
    _NAME = _CHARACTER_CLASS.__name__.lower()

    # Configuration File
    CONFIG_FILENAME = '{}.config'.format(_NAME)
    DEFAULT_CONFIG_FILE_LOCATION = os.path.join(DEFAULT_CONFIG_ROOT, CONFIG_FILENAME)

    # Database
    DEFAULT_DB_NAME = '{}.db'.format(_NAME)
    DEFAULT_DB_FILEPATH = os.path.join(DEFAULT_CONFIG_ROOT, DEFAULT_DB_NAME)

    # Network
    DEFAULT_REST_PORT = 6151
    DEFAULT_LEARNER_PORT = 9151

    @property
    def static_payload(self) -> dict:
        payload = dict(
         rest_host=self.rest_host,
         rest_port=self.rest_port,
         db_filepath=self.db_filepath,
        )
        return {**super().static_payload, **payload}

    def write_keyring(self, password: str, **generation_kwargs) -> NucypherKeyring:

        return super().write_keyring(password=password,
                                     encrypting=True,  # TODO: #668
                                     rest=True,
                                     host=self.rest_host,
                                     curve=self.tls_curve,
                                     **generation_kwargs)
