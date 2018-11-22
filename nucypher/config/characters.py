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

from web3.middleware import geth_poa_middleware

from constant_sorrow.constants import (
    UNINITIALIZED_CONFIGURATION,
    NO_KEYRING_ATTACHED
)
from nucypher.blockchain.eth.agents import NucypherTokenAgent, MinerAgent
from nucypher.blockchain.eth.chains import Blockchain
from nucypher.config.constants import DEFAULT_CONFIG_ROOT
from nucypher.config.node import NodeConfiguration


class UrsulaConfiguration(NodeConfiguration):
    from nucypher.characters.lawful import Ursula

    _CHARACTER_CLASS = Ursula
    _NAME = 'ursula'

    CONFIG_FILENAME = '{}.config'.format(_NAME)
    DEFAULT_CONFIG_FILE_LOCATION = os.path.join(DEFAULT_CONFIG_ROOT, CONFIG_FILENAME)
    DEFAULT_DB_NAME = '{}.db'.format(_NAME)

    def __init__(self, db_filepath: str = None, *args, **kwargs) -> None:
        self.db_filepath = db_filepath or UNINITIALIZED_CONFIGURATION
        super().__init__(*args, **kwargs)

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

        # Build a merged dict of Ursula parameters
        merged_parameters = {**self.static_payload, **self.dynamic_payload, **overrides}

        #
        # Pre-Init
        #

        # Verify the configuration file refers to the same configuration root as this instance
        config_root_from_config_file = merged_parameters.pop('config_root')
        if config_root_from_config_file != self.config_root:
            message = "Configuration root mismatch {} and {}.".format(config_root_from_config_file, self.config_root)
            raise self.ConfigurationError(message)

        if self.federated_only is False:

            self.blockchain = Blockchain.connect(provider_uri=self.provider_uri)

            if self.poa:
                w3 = self.miner_agent.blockchain.interface.w3
                w3.middleware_stack.inject(geth_poa_middleware, layer=0)

            self.token_agent = NucypherTokenAgent(blockchain=self.blockchain)
            self.miner_agent = MinerAgent(blockchain=self.blockchain)
            merged_parameters.update(blockchain=self.blockchain)

        #
        # Init
        #
        ursula = self._CHARACTER_CLASS(**merged_parameters)

        #
        # Post-Init
        #
        if self.dev_mode:
            class MockDatastoreThreadPool(object):
                def callInThread(self, f, *args, **kwargs):
                    return f(*args, **kwargs)
            ursula.datastore_threadpool = MockDatastoreThreadPool()

        return ursula

    def __write(self, password: str, no_registry: bool):
        _new_installation_path = self.initialize(password=password, import_registry=no_registry)
        _configuration_filepath = self.to_configuration_file(filepath=self.config_file_location)

    @classmethod
    def generate(cls, password: str, no_registry: bool, *args, **kwargs) -> 'UrsulaConfiguration':
        """Hook-up a new initial installation and write configuration file to the disk"""
        ursula_config = cls(dev_mode=False, is_me=True, *args, **kwargs)
        ursula_config.__write(password=password, no_registry=no_registry)
        return ursula_config


class AliceConfiguration(NodeConfiguration):
    from nucypher.characters.lawful import Alice

    _CHARACTER_CLASS = Alice
    _NAME = 'alice'

    CONFIG_FILENAME = '{}.config'.format(_NAME)
    DEFAULT_CONFIG_FILE_LOCATION = os.path.join(DEFAULT_CONFIG_ROOT, CONFIG_FILENAME)


class BobConfiguration(NodeConfiguration):
    from nucypher.characters.lawful import Bob

    _CHARACTER_CLASS = Bob
    _NAME = 'bob'

    CONFIG_FILENAME = '{}.config'.format(_NAME)
    DEFAULT_CONFIG_FILE_LOCATION = os.path.join(DEFAULT_CONFIG_ROOT, CONFIG_FILENAME)
