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

from constant_sorrow.constants import UNINITIALIZED_CONFIGURATION
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.ec import EllipticCurve
from cryptography.x509 import Certificate
from eth_utils import is_checksum_address

from nucypher.blockchain.eth.actors import StakeHolder
from nucypher.config.base import CharacterConfiguration
from nucypher.config.constants import (
    DEFAULT_CONFIG_ROOT,
    NUCYPHER_ENVVAR_WORKER_ETH_PASSWORD,
    NUCYPHER_ENVVAR_ALICE_ETH_PASSWORD,
    NUCYPHER_ENVVAR_BOB_ETH_PASSWORD
)
from nucypher.config.keyring import NucypherKeyring
from nucypher.utilities.networking import LOOPBACK_ADDRESS


class UrsulaConfiguration(CharacterConfiguration):

    from nucypher.characters.lawful import Ursula
    CHARACTER_CLASS = Ursula
    NAME = CHARACTER_CLASS.__name__.lower()

    DEFAULT_REST_PORT = 9151
    DEFAULT_DEVELOPMENT_REST_HOST = LOOPBACK_ADDRESS
    DEFAULT_DEVELOPMENT_REST_PORT = 10151
    DEFAULT_DB_NAME = f'{NAME}.db'
    DEFAULT_AVAILABILITY_CHECKS = False
    LOCAL_SIGNERS_ALLOWED = True
    SIGNER_ENVVAR = NUCYPHER_ENVVAR_WORKER_ETH_PASSWORD

    def __init__(self,
                 rest_host: str = None,
                 worker_address: str = None,
                 dev_mode: bool = False,
                 db_filepath: str = None,
                 rest_port: int = None,
                 certificate: Certificate = None,
                 availability_check: bool = None,
                 *args, **kwargs) -> None:

        if dev_mode:
            rest_host = rest_host or self.DEFAULT_DEVELOPMENT_REST_HOST
            if not rest_port:
                rest_port = self.DEFAULT_DEVELOPMENT_REST_PORT
        else:
            if not rest_host:
                raise ValueError('rest_host is required for live workers.')
            if not rest_port:
                rest_port = self.DEFAULT_REST_PORT

        self.rest_port = rest_port
        self.rest_host = rest_host
        self.certificate = certificate
        self.db_filepath = db_filepath or UNINITIALIZED_CONFIGURATION
        self.worker_address = worker_address
        self.availability_check = availability_check if availability_check is not None else self.DEFAULT_AVAILABILITY_CHECKS
        super().__init__(dev_mode=dev_mode, *args, **kwargs)

    @classmethod
    def checksum_address_from_filepath(cls, filepath: str) -> str:
        """
        Extracts worker address by "peeking" inside the ursula configuration file.
        """

        checksum_address = cls.peek(filepath=filepath, field='checksum_address')
        federated = bool(cls.peek(filepath=filepath, field='federated_only'))
        if not federated:
            checksum_address = cls.peek(filepath=filepath, field='worker_address')

        if not is_checksum_address(checksum_address):
            raise RuntimeError(f"Invalid checksum address detected in configuration file at '{filepath}'.")
        return checksum_address

    def generate_runtime_filepaths(self, config_root: str) -> dict:
        base_filepaths = super().generate_runtime_filepaths(config_root=config_root)
        filepaths = dict(db_filepath=os.path.join(config_root, self.DEFAULT_DB_NAME))
        base_filepaths.update(filepaths)
        return base_filepaths

    def generate_filepath(self, modifier: str = None, *args, **kwargs) -> str:
        filepath = super().generate_filepath(modifier=modifier or self.keyring.signing_public_key.hex()[:8], *args, **kwargs)
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
    NAME = CHARACTER_CLASS.__name__.lower()

    DEFAULT_CONTROLLER_PORT = 8151

    # TODO: Best (Sane) Defaults
    DEFAULT_M = 2
    DEFAULT_N = 3

    DEFAULT_STORE_POLICIES = True
    DEFAULT_STORE_CARDS = True

    SIGNER_ENVVAR = NUCYPHER_ENVVAR_ALICE_ETH_PASSWORD

    _CONFIG_FIELDS = (
        *CharacterConfiguration._CONFIG_FIELDS,
        'store_policies',
        'store_cards'
    )

    def __init__(self,
                 m: int = None,
                 n: int = None,
                 rate: int = None,
                 payment_periods: int = None,
                 store_policies: bool = DEFAULT_STORE_POLICIES,
                 store_cards: bool = DEFAULT_STORE_CARDS,
                 *args, **kwargs):

        super().__init__(*args, **kwargs)
        self.m = m or self.DEFAULT_M
        self.n = n or self.DEFAULT_N

        # if not self.federated_only:  # TODO: why not?
        self.rate = rate
        self.payment_periods = payment_periods

        self.store_policies = store_policies
        self.store_cards = store_cards

    def static_payload(self) -> dict:
        payload = dict(
            m=self.m,
            n=self.n,
            store_policies=self.store_policies,
            store_cards=self.store_cards
        )
        if not self.federated_only:
            if self.rate:
                payload['rate'] = self.rate
            if self.payment_periods:
                payload['payment_periods'] = self.payment_periods
        return {**super().static_payload(), **payload}

    def write_keyring(self, password: str, **generation_kwargs) -> NucypherKeyring:
        return super().write_keyring(password=password,
                                     encrypting=True,
                                     rest=False,
                                     **generation_kwargs)


class BobConfiguration(CharacterConfiguration):
    from nucypher.characters.lawful import Bob

    CHARACTER_CLASS = Bob
    NAME = CHARACTER_CLASS.__name__.lower()
    DEFAULT_CONTROLLER_PORT = 7151
    DEFFAULT_STORE_POLICIES = True
    DEFAULT_STORE_CARDS = True
    SIGNER_ENVVAR = NUCYPHER_ENVVAR_BOB_ETH_PASSWORD

    _CONFIG_FIELDS = (
        *CharacterConfiguration._CONFIG_FIELDS,
        'store_policies',
        'store_cards'
    )

    def __init__(self,
                 store_policies: bool = DEFFAULT_STORE_POLICIES,
                 store_cards: bool = DEFAULT_STORE_CARDS,
                 *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.store_policies = store_policies
        self.store_cards = store_cards

    def write_keyring(self, password: str, **generation_kwargs) -> NucypherKeyring:
        return super().write_keyring(password=password,
                                     encrypting=True,
                                     rest=False,
                                     **generation_kwargs)

    def static_payload(self) -> dict:
        payload = dict(
            store_policies=self.store_policies,
            store_cards=self.store_cards
        )
        return {**super().static_payload(), **payload}


class FelixConfiguration(CharacterConfiguration):
    from nucypher.characters.chaotic import Felix

    # Character
    CHARACTER_CLASS = Felix
    NAME = CHARACTER_CLASS.__name__.lower()

    DEFAULT_DB_NAME = '{}.db'.format(NAME)
    DEFAULT_DB_FILEPATH = os.path.join(DEFAULT_CONFIG_ROOT, DEFAULT_DB_NAME)
    DEFAULT_REST_PORT = 6151
    DEFAULT_LEARNER_PORT = 9151
    DEFAULT_REST_HOST = LOOPBACK_ADDRESS
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
         signer_uri=self.signer_uri
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

    NAME = 'stakeholder'
    CHARACTER_CLASS = StakeHolder

    _CONFIG_FIELDS = (
        *CharacterConfiguration._CONFIG_FIELDS,
        'provider_uri'
    )

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
                       domain=self.domain,
                       signer_uri=self.signer_uri,
                       worker_data=self.worker_data
                       )

        if self.registry_filepath:
            payload.update(dict(registry_filepath=self.registry_filepath))
        return payload

    @property
    def dynamic_payload(self) -> dict:
        payload = dict(registry=self.registry, signer=self.signer)
        return payload

    def _setup_node_storage(self, node_storage=None) -> None:
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
        """Shortcut: Hook-up a new initial installation configuration."""
        node_config = cls(dev_mode=False, *args, **kwargs)
        node_config.initialize()
        return node_config

    def to_configuration_file(self, override: bool = True, *args, **kwargs) -> str:
        return super().to_configuration_file(override=True, *args, **kwargs)
