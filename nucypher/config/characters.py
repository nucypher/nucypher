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
    _NAME = 'ursula'

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
                                     wallet=not self.federated_only,
                                     host=self.rest_host,
                                     curve=self.tls_curve,
                                     **generation_kwargs)


class AliceConfiguration(NodeConfiguration):
    from nucypher.characters.lawful import Alice

    _CHARACTER_CLASS = Alice
    _NAME = 'alice'

    CONFIG_FILENAME = '{}.config'.format(_NAME)
    DEFAULT_CONFIG_FILE_LOCATION = os.path.join(DEFAULT_CONFIG_ROOT, CONFIG_FILENAME)

    def write_keyring(self, password: str, **generation_kwargs) -> NucypherKeyring:

        return super().write_keyring(password=password,
                                     encrypting=True,
                                     wallet=not self.federated_only,
                                     rest=False)


class BobConfiguration(NodeConfiguration):
    from nucypher.characters.lawful import Bob

    _CHARACTER_CLASS = Bob
    _NAME = 'bob'

    CONFIG_FILENAME = '{}.config'.format(_NAME)
    DEFAULT_CONFIG_FILE_LOCATION = os.path.join(DEFAULT_CONFIG_ROOT, CONFIG_FILENAME)
