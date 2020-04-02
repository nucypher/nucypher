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

from constant_sorrow.constants import (
    UNINITIALIZED_CONFIGURATION
)
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.ec import EllipticCurve
from cryptography.x509 import Certificate

from nucypher.blockchain.eth.actors import StakeHolder
from nucypher.blockchain.eth.signers import Signer
from nucypher.config.constants import DEFAULT_CONFIG_ROOT
from nucypher.config.keyring import NucypherKeyring
from nucypher.config.node import CharacterConfiguration


class UrsulaConfiguration(CharacterConfiguration):

    from nucypher.characters.lawful import Ursula
    CHARACTER_CLASS = Ursula
    _NAME = CHARACTER_CLASS.__name__.lower()

    DEFAULT_REST_HOST = '127.0.0.1'
    DEFAULT_REST_PORT = 9151
    DEFAULT_DEVELOPMENT_REST_PORT = 10151
    __DEFAULT_TLS_CURVE = ec.SECP384R1
    DEFAULT_DB_NAME = '{}.db'.format(_NAME)
    DEFAULT_AVAILABILITY_CHECKS = True

    def __init__(self,
                 worker_address: str = None,
                 dev_mode: bool = False,
                 db_filepath: str = None,
                 rest_host: str = None,
                 rest_port: int = None,
                 tls_curve: EllipticCurve = None,
                 certificate: Certificate = None,
                 availability_check: bool = None,
                 *args, **kwargs) -> None:

        if not rest_port:
            if dev_mode:
                rest_port = self.DEFAULT_DEVELOPMENT_REST_PORT
            else:
                rest_port = self.DEFAULT_REST_PORT
        self.rest_port = rest_port
        self.rest_host = rest_host or self.DEFAULT_REST_HOST
        self.tls_curve = tls_curve or self.__DEFAULT_TLS_CURVE
        self.certificate = certificate
        self.db_filepath = db_filepath or UNINITIALIZED_CONFIGURATION
        self.worker_address = worker_address
        self.availability_check = availability_check if availability_check is not None else self.DEFAULT_AVAILABILITY_CHECKS
        super().__init__(dev_mode=dev_mode, *args, **kwargs)

    def generate_runtime_filepaths(self, config_root: str) -> dict:
        base_filepaths = super().generate_runtime_filepaths(config_root=config_root)
        filepaths = dict(db_filepath=os.path.join(config_root, self.DEFAULT_DB_NAME))
        base_filepaths.update(filepaths)
        return base_filepaths

    def generate_filepath(self, modifier: str = None, *args, **kwargs) -> str:
        filepath = super().generate_filepath(modifier=modifier or self.worker_address, *args, **kwargs)
        return filepath

    def static_payload(self) -> dict:
        payload = dict(
            worker_address=self.worker_address,
            rest_host=self.rest_host,
            rest_port=self.rest_port,
            db_filepath=self.db_filepath,
            availability_check=self.availability_check,
        )
        return {**super().static_payload(), **payload}

    @property
    def dynamic_payload(self) -> dict:
        payload = dict(
            network_middleware=self.network_middleware,
            tls_curve=self.tls_curve,  # TODO: Needs to be in static payload with [str -> curve] mapping
            certificate=self.certificate,
            interface_signature=self.interface_signature,
            timestamp=None
        )
        return {**super().dynamic_payload, **payload}

    def produce(self, **overrides):
        """Produce a new Ursula from configuration"""

        merged_parameters = self.generate_parameters(**overrides)
        ursula = self.CHARACTER_CLASS(**merged_parameters)

        if self.dev_mode:
            class MockDatastoreThreadPool(object):
                def callInThread(self, f, *args, **kwargs):
                    return f(*args, **kwargs)
            ursula.datastore_threadpool = MockDatastoreThreadPool()

        return ursula

    def attach_keyring(self, checksum_address: str = None, *args, **kwargs) -> None:
        if self.federated_only:
            account = checksum_address or self.checksum_address
        else:
            account = checksum_address or self.worker_address
        return super().attach_keyring(checksum_address=account)

    def write_keyring(self, password: str, **generation_kwargs) -> NucypherKeyring:
        keyring = super().write_keyring(password=password,
                                        encrypting=True,
                                        rest=True,
                                        host=self.rest_host,
                                        curve=self.tls_curve,
                                        checksum_address=self.worker_address,
                                        **generation_kwargs)
        return keyring

    def destroy(self) -> None:
        if os.path.isfile(self.db_filepath):
            os.remove(self.db_filepath)
        super().destroy()


class AliceConfiguration(CharacterConfiguration):
    from nucypher.characters.lawful import Alice

    CHARACTER_CLASS = Alice
    _NAME = CHARACTER_CLASS.__name__.lower()

    DEFAULT_CONTROLLER_PORT = 8151

    # TODO: Best (Sane) Defaults
    DEFAULT_M = 2
    DEFAULT_N = 3
    DEFAULT_FIRST_PERIOD_REWARD = 0   # TODO #1063

    def __init__(self,
                 m: int = None,
                 n: int = None,
                 rate: int = None,
                 duration_periods: int = None,
                 *args, **kwargs):

        super().__init__(*args, **kwargs)
        self.m = m or self.DEFAULT_M
        self.n = n or self.DEFAULT_N

        # if not self.federated_only:  # TODO: why not?
        self.rate = rate
        self.duration_periods = duration_periods

    def static_payload(self) -> dict:
        payload = dict(m=self.m, n=self.n)
        if not self.federated_only:
            if self.rate:
                payload['rate'] = self.rate
            if self.duration_periods:
                payload['duration_periods'] = self.duration_periods
        return {**super().static_payload(), **payload}

    def write_keyring(self, password: str, **generation_kwargs) -> NucypherKeyring:
        return super().write_keyring(password=password,
                                     encrypting=True,
                                     rest=False,
                                     **generation_kwargs)


class BobConfiguration(CharacterConfiguration):
    from nucypher.characters.lawful import Bob

    CHARACTER_CLASS = Bob
    _NAME = CHARACTER_CLASS.__name__.lower()

    DEFAULT_CONTROLLER_PORT = 7151

    def write_keyring(self, password: str, **generation_kwargs) -> NucypherKeyring:
        return super().write_keyring(password=password,
                                     encrypting=True,
                                     rest=False,
                                     **generation_kwargs)


class FelixConfiguration(CharacterConfiguration):
    from nucypher.characters.chaotic import Felix

    # Character
    CHARACTER_CLASS = Felix
    _NAME = CHARACTER_CLASS.__name__.lower()

    DEFAULT_DB_NAME = '{}.db'.format(_NAME)
    DEFAULT_DB_FILEPATH = os.path.join(DEFAULT_CONFIG_ROOT, DEFAULT_DB_NAME)
    DEFAULT_REST_PORT = 6151
    DEFAULT_LEARNER_PORT = 9151
    DEFAULT_REST_HOST = '127.0.0.1'
    __DEFAULT_TLS_CURVE = ec.SECP384R1

    def __init__(self,
                 db_filepath: str = None,
                 rest_host: str = None,
                 rest_port: int = None,
                 tls_curve: EllipticCurve = None,
                 certificate: Certificate = None,
                 *args, **kwargs) -> None:

        super().__init__(*args, **kwargs)
        if not rest_port:
            rest_port = self.DEFAULT_REST_PORT
        self.rest_port = rest_port or self.DEFAULT_REST_PORT
        self.rest_host = rest_host or self.DEFAULT_REST_HOST
        self.tls_curve = tls_curve or self.__DEFAULT_TLS_CURVE
        self.certificate = certificate
        self.db_filepath = db_filepath or os.path.join(self.config_root, self.DEFAULT_DB_NAME)

    def static_payload(self) -> dict:
        payload = dict(
         rest_host=self.rest_host,
         rest_port=self.rest_port,
         db_filepath=self.db_filepath,
        )
        return {**super().static_payload(), **payload}

    def write_keyring(self, password: str, **generation_kwargs) -> NucypherKeyring:
        return super().write_keyring(password=password,
                                     encrypting=True,  # TODO: #668
                                     rest=True,
                                     host=self.rest_host,
                                     curve=self.tls_curve,
                                     **generation_kwargs)


class StakeHolderConfiguration(CharacterConfiguration):

    _NAME = 'stakeholder'
    CHARACTER_CLASS = StakeHolder

    def __init__(self, checksum_addresses: set = None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.checksum_addresses = checksum_addresses

    def static_payload(self) -> dict:
        """Values to read/write from stakeholder JSON configuration files"""
        if not self.signer_uri:
            self.signer_uri = self.provider_uri
        payload = dict(provider_uri=self.provider_uri,
                       poa=self.poa,
                       light=self.is_light,
                       domains=list(self.domains),
                       # TODO: Move empty collection casting to base
                       checksum_addresses=self.checksum_addresses or list(),
                       signer_uri=self.signer_uri)

        if self.registry_filepath:
            payload.update(dict(registry_filepath=self.registry_filepath))
        return payload

    @property
    def dynamic_payload(self) -> dict:
        payload = dict(registry=self.registry, signer=Signer.from_signer_uri(self.signer_uri))
        return payload

    def __setup_node_storage(self, node_storage=None) -> None:
        pass

    @classmethod
    def assemble(cls, filepath: str = None, **overrides) -> dict:
        payload = cls._read_configuration_file(filepath=filepath)
        # Filter out None values from **overrides to detect, well, overrides...
        # Acts as a shim for optional CLI flags.
        overrides = {k: v for k, v in overrides.items() if v is not None}
        payload = {**payload, **overrides}
        return payload

    @classmethod
    def generate_runtime_filepaths(cls, config_root: str) -> dict:
        """Dynamically generate paths based on configuration root directory"""
        filepaths = dict(config_root=config_root,
                         config_file_location=os.path.join(config_root, cls.generate_filename()))
        return filepaths

    def initialize(self, password: str = None) -> str:
        """Initialize a new configuration and write installation files to disk."""

        # Development
        if self.dev_mode:
            self.__temp_dir = TemporaryDirectory(prefix=self.TEMP_CONFIGURATION_DIR_PREFIX)
            self.config_root = self.__temp_dir.name

        # Persistent
        else:
            self._ensure_config_root_exists()

        self._cache_runtime_filepaths()

        # Validate
        if not self.dev_mode:
            self.validate()

        # Success
        message = "Created nucypher installation files at {}".format(self.config_root)
        self.log.debug(message)
        return self.config_root

    @classmethod
    def generate(cls, *args, **kwargs):
        """Shortcut: Hook-up a new initial installation and write configuration file to the disk"""
        node_config = cls(dev_mode=False, *args, **kwargs)
        node_config.initialize()
        node_config.to_configuration_file()
        return node_config

    def to_configuration_file(self, override: bool = True, *args, **kwargs) -> str:
        return super().to_configuration_file(override=True, *args, **kwargs)
