import json
from pathlib import Path
from typing import Dict, List, Optional

from cryptography.x509 import Certificate

from nucypher.config.base import CharacterConfiguration
from nucypher.config.constants import (
    NUCYPHER_ENVVAR_ALICE_ETH_PASSWORD,
    NUCYPHER_ENVVAR_BOB_ETH_PASSWORD,
    NUCYPHER_ENVVAR_OPERATOR_ETH_PASSWORD,
)
from nucypher.crypto.keystore import Keystore
from nucypher.utilities.networking import LOOPBACK_ADDRESS


class UrsulaConfiguration(CharacterConfiguration):

    from nucypher.characters.lawful import Ursula
    CHARACTER_CLASS = Ursula
    NAME = CHARACTER_CLASS.__name__.lower()

    # Network
    DEFAULT_REST_PORT = 9151
    DEFAULT_DEVELOPMENT_REST_HOST = LOOPBACK_ADDRESS
    DEFAULT_DEVELOPMENT_REST_PORT = 10151

    # Wallet
    MNEMONIC_KEYSTORE = True
    WALLET_FILEPATH_ENVVAR = NUCYPHER_ENVVAR_OPERATOR_ETH_PASSWORD
    DEFAULT_WALLET_FILEPATH = Keystore._DEFAULT_DIR / 'operator.json'

    def __init__(
        self,
        dev_mode: bool = False,
        rest_host: Optional[str] = None,
        rest_port: Optional[int] = None,
        certificate: Optional[Certificate] = None,
        condition_blockchain_endpoints: Optional[Dict[str, List[str]]] = None,
        *args, **kwargs,
    ) -> None:

        if dev_mode:
            rest_host = rest_host or self.DEFAULT_DEVELOPMENT_REST_HOST
            rest_port = rest_port or self.DEFAULT_DEVELOPMENT_REST_PORT
        else:
            if not rest_host:
                raise ValueError("rest_host is required for live nodes.")
            rest_port = rest_port or self.DEFAULT_REST_PORT

        self.rest_port = rest_port
        self.rest_host = rest_host
        self.certificate = certificate

        super().__init__(dev_mode=dev_mode, *args, **kwargs)

        # json configurations don't allow for integer keyed dictionaries
        # so convert string chain id to integer
        self.condition_blockchain_endpoints = dict()
        if condition_blockchain_endpoints:
            for chain, blockchain_endpoint in condition_blockchain_endpoints.items():
                # convert chain from string key (for json) to integer
                self.condition_blockchain_endpoints[int(chain)] = blockchain_endpoint
        self.configure_condition_blockchain_endpoints()

    def configure_condition_blockchain_endpoints(self) -> None:
        """Configure default condition provider URIs for eth and polygon network."""
        # Polygon
        polygon_chain_id = self.domain.polygon_chain.id
        polygon_endpoints = self.condition_blockchain_endpoints.get(
            polygon_chain_id, []
        )
        if not polygon_endpoints:
            self.condition_blockchain_endpoints[polygon_chain_id] = polygon_endpoints

        if self.polygon_endpoint not in polygon_endpoints:
            polygon_endpoints.append(self.polygon_endpoint)

        # Ethereum
        staking_chain_id = self.domain.eth_chain.id
        staking_chain_endpoints = self.condition_blockchain_endpoints.get(
            staking_chain_id, []
        )
        if not staking_chain_endpoints:
            self.condition_blockchain_endpoints[
                staking_chain_id
            ] = staking_chain_endpoints

        if self.eth_endpoint not in staking_chain_endpoints:
            staking_chain_endpoints.append(self.eth_endpoint)

    def generate_runtime_filepaths(self, config_root: Path) -> dict:
        base_filepaths = super().generate_runtime_filepaths(config_root=config_root)
        return base_filepaths

    def static_payload(self) -> dict:
        payload = dict(
            rest_host=self.rest_host,
            rest_port=self.rest_port,
            wallet_filepath=self.wallet_filepath,
            condition_blockchain_endpoints=self.condition_blockchain_endpoints,
        )
        return {**super().static_payload(), **payload}

    @property
    def dynamic_payload(self) -> dict:
        payload = dict(
            certificate=self.certificate,
            network_middleware=self.network_middleware,
            pre_payment_method=self.configure_pre_payment_method(),
        )
        return {**super().dynamic_payload, **payload}

    def produce(self, **overrides):
        """Produce a new Ursula from configuration"""
        merged_parameters = self.generate_parameters(**overrides)
        ursula = self.CHARACTER_CLASS(**merged_parameters)
        return ursula

    @classmethod
    def deserialize(cls, payload: str, deserializer=json.loads, payload_label: Optional[str] = None) -> dict:
        deserialized_payload = super().deserialize(payload, deserializer, payload_label)
        return deserialized_payload

    @classmethod
    def assemble(cls, filepath: Optional[Path] = None, **overrides) -> dict:
        payload = super().assemble(filepath, **overrides)
        return payload


class AliceConfiguration(CharacterConfiguration):
    from nucypher.characters.lawful import Alice

    CHARACTER_CLASS = Alice
    NAME = CHARACTER_CLASS.__name__.lower()

    # TODO: Best (Sane) Defaults
    DEFAULT_THRESHOLD = 2
    DEFAULT_SHARES = 3
    WALLET_FILEPATH_ENVVAR = NUCYPHER_ENVVAR_ALICE_ETH_PASSWORD
    _CONFIG_FIELDS = (*CharacterConfiguration._CONFIG_FIELDS,)

    def __init__(self,
                 threshold: int = None,
                 shares: int = None,
                 rate: int = None,
                 duration: int = None,
                 *args, **kwargs):

        super().__init__(*args, **kwargs)

        # Policy Value Defaults
        self.rate = rate
        self.duration = duration
        self.threshold = threshold or self.DEFAULT_THRESHOLD
        self.shares = shares or self.DEFAULT_SHARES

    def static_payload(self) -> dict:
        payload = dict(
            threshold=self.threshold,
            shares=self.shares,
            pre_payment_method=self.pre_payment_method,
            rate=self.rate,
            duration=self.duration,
        )
        return {**super().static_payload(), **payload}

    @property
    def dynamic_payload(self) -> dict:
        payload = dict(pre_payment_method=self.configure_pre_payment_method())
        return {**super().dynamic_payload, **payload}


class BobConfiguration(CharacterConfiguration):
    from nucypher.characters.lawful import Bob

    CHARACTER_CLASS = Bob
    NAME = CHARACTER_CLASS.__name__.lower()
    WALLET_FILEPATH_ENVVAR = NUCYPHER_ENVVAR_BOB_ETH_PASSWORD
    _CONFIG_FIELDS = (*CharacterConfiguration._CONFIG_FIELDS,)
