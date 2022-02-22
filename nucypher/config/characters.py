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


import json
from pathlib import Path
from typing import Optional

from constant_sorrow.constants import UNINITIALIZED_CONFIGURATION
from cryptography.x509 import Certificate
from eth_utils import is_checksum_address

from nucypher.config.base import CharacterConfiguration
from nucypher.config.constants import (
    NUCYPHER_ENVVAR_OPERATOR_ETH_PASSWORD,
    NUCYPHER_ENVVAR_ALICE_ETH_PASSWORD,
    NUCYPHER_ENVVAR_BOB_ETH_PASSWORD
)
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
    SIGNER_ENVVAR = NUCYPHER_ENVVAR_OPERATOR_ETH_PASSWORD
    MNEMONIC_KEYSTORE = True

    def __init__(self,
                 rest_host: str = None,
                 operator_address: str = None,
                 dev_mode: bool = False,
                 db_filepath: Optional[Path] = None,
                 keystore_path: Optional[Path] = None,
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
        self.operator_address = operator_address
        self.availability_check = availability_check if availability_check is not None else self.DEFAULT_AVAILABILITY_CHECKS
        super().__init__(dev_mode=dev_mode, keystore_path=keystore_path, *args, **kwargs)

    @classmethod
    def checksum_address_from_filepath(cls, filepath: Path) -> str:
        """
        Extracts worker address by "peeking" inside the ursula configuration file.
        """
        checksum_address = cls.peek(filepath=filepath, field='checksum_address')
        federated = bool(cls.peek(filepath=filepath, field='federated_only'))
        if not federated:
            checksum_address = cls.peek(filepath=filepath, field='operator_address')

        if not is_checksum_address(checksum_address):
            raise RuntimeError(f"Invalid checksum address detected in configuration file at '{filepath}'.")
        return checksum_address

    def generate_runtime_filepaths(self, config_root: Path) -> dict:
        base_filepaths = super().generate_runtime_filepaths(config_root=config_root)
        filepaths = dict(db_filepath=config_root / self.DEFAULT_DB_NAME)
        base_filepaths.update(filepaths)
        return base_filepaths

    def generate_filepath(self, modifier: str = None, *args, **kwargs) -> Path:
        filepath = super().generate_filepath(modifier=modifier or self.keystore.id[:8], *args, **kwargs)
        return filepath

    def static_payload(self) -> dict:
        payload = dict(
            operator_address=self.operator_address,
            rest_host=self.rest_host,
            rest_port=self.rest_port,
            db_filepath=self.db_filepath,
            availability_check=self.availability_check,

            # TODO: Resolve variable prefixing below (uses nested configuration fields?)
            payment_method=self.payment_method,
            payment_provider=self.payment_provider,
            payment_network=self.payment_network
        )
        return {**super().static_payload(), **payload}

    @property
    def dynamic_payload(self) -> dict:
        payload = dict(
            network_middleware=self.network_middleware,
            certificate=self.certificate,
            payment_method=self.configure_payment_method()
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

    def destroy(self) -> None:
        if self.db_filepath.is_file():
            self.db_filepath.unlink()
        super().destroy()

    @classmethod
    def deserialize(cls, payload: str, deserializer=json.loads, payload_label: Optional[str] = None) -> dict:
        deserialized_payload = super().deserialize(payload, deserializer, payload_label)
        deserialized_payload['db_filepath'] = Path(deserialized_payload['db_filepath'])
        return deserialized_payload

    @classmethod
    def assemble(cls, filepath: Optional[Path] = None, **overrides) -> dict:
        payload = super().assemble(filepath, **overrides)
        payload['db_filepath'] = Path(payload['db_filepath'])  # TODO: this can be moved to dynamic payload
        return payload


class AliceConfiguration(CharacterConfiguration):
    from nucypher.characters.lawful import Alice

    CHARACTER_CLASS = Alice
    NAME = CHARACTER_CLASS.__name__.lower()

    DEFAULT_CONTROLLER_PORT = 8151

    # TODO: Best (Sane) Defaults
    DEFAULT_THRESHOLD = 2
    DEFAULT_SHARES = 3

    DEFAULT_STORE_POLICIES = True
    DEFAULT_STORE_CARDS = True

    SIGNER_ENVVAR = NUCYPHER_ENVVAR_ALICE_ETH_PASSWORD

    _CONFIG_FIELDS = (
        *CharacterConfiguration._CONFIG_FIELDS,
        'store_policies',
        'store_cards',
    )

    def __init__(self,
                 threshold: int = None,
                 shares: int = None,
                 rate: int = None,
                 duration: int = None,
                 store_policies: bool = DEFAULT_STORE_POLICIES,
                 store_cards: bool = DEFAULT_STORE_CARDS,
                 *args, **kwargs):

        super().__init__(*args, **kwargs)

        # Storage
        self.store_policies = store_policies
        self.store_cards = store_cards

        # Policy Value Defaults
        self.rate = rate
        self.duration = duration
        self.threshold = threshold or self.DEFAULT_THRESHOLD
        self.shares = shares or self.DEFAULT_SHARES

    def static_payload(self) -> dict:
        payload = dict(
            threshold=self.threshold,
            shares=self.shares,
            store_policies=self.store_policies,
            store_cards=self.store_cards,
            payment_network=self.payment_network,
            payment_provider=self.payment_provider,
            payment_method=self.payment_method
        )
        if not self.federated_only:
            if self.rate:
                payload['rate'] = self.rate
            if self.duration:
                payload['duration'] = self.duration
        return {**super().static_payload(), **payload}

    @property
    def dynamic_payload(self) -> dict:
        payload = dict(payment_method=self.configure_payment_method())
        return {**super().dynamic_payload, **payload}


class BobConfiguration(CharacterConfiguration):
    from nucypher.characters.lawful import Bob

    CHARACTER_CLASS = Bob
    NAME = CHARACTER_CLASS.__name__.lower()
    DEFAULT_CONTROLLER_PORT = 7151
    DEFAULT_STORE_POLICIES = True
    DEFAULT_STORE_CARDS = True
    SIGNER_ENVVAR = NUCYPHER_ENVVAR_BOB_ETH_PASSWORD

    _CONFIG_FIELDS = (
        *CharacterConfiguration._CONFIG_FIELDS,
        'store_policies',
        'store_cards'
    )

    def __init__(self,
                 store_policies: bool = DEFAULT_STORE_POLICIES,
                 store_cards: bool = DEFAULT_STORE_CARDS,
                 *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.store_policies = store_policies
        self.store_cards = store_cards

    def static_payload(self) -> dict:
        payload = dict(
            store_policies=self.store_policies,
            store_cards=self.store_cards
        )
        return {**super().static_payload(), **payload}
