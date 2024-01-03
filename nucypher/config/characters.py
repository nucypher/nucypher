import json
from pathlib import Path
from typing import Dict, List, Optional

from cryptography.x509 import Certificate
from eth_utils import is_checksum_address

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

    DEFAULT_REST_PORT = 9151
    DEFAULT_DEVELOPMENT_REST_HOST = LOOPBACK_ADDRESS
    DEFAULT_DEVELOPMENT_REST_PORT = 10151
    LOCAL_SIGNERS_ALLOWED = True
    SIGNER_ENVVAR = NUCYPHER_ENVVAR_OPERATOR_ETH_PASSWORD
    MNEMONIC_KEYSTORE = True
    DEFAULT_WALLET_FILEPATH = Keystore._DEFAULT_DIR / 'operator.json'

    def __init__(
        self,
        rest_host: Optional[str] = None,
        operator_address: Optional[str] = None,
        dev_mode: bool = False,
        keystore_path: Optional[Path] = None,
        rest_port: Optional[int] = None,
        certificate: Optional[Certificate] = None,
        condition_blockchain_endpoints: Optional[Dict[str, List[str]]] = None,
        signer_uri: Optional[str] = None,
        wallet_filepath: Optional[Path] = None,
        *args, **kwargs,
    ) -> None:

        if dev_mode:
            rest_host = rest_host or self.DEFAULT_DEVELOPMENT_REST_HOST
            if not rest_port:
                rest_port = self.DEFAULT_DEVELOPMENT_REST_PORT
        else:
            if not rest_host:
                raise ValueError("rest_host is required for live nodes.")
            if not rest_port:
                rest_port = self.DEFAULT_REST_PORT

        self.rest_port = rest_port
        self.rest_host = rest_host
        self.certificate = certificate

        if signer_uri and wallet_filepath:
            raise ValueError("Cannot specify both a signer URI and a wallet filepath.")
        if not signer_uri and not wallet_filepath:
            wallet_filepath = self.DEFAULT_WALLET_FILEPATH
        self.operator_address = operator_address

        super().__init__(
            dev_mode=dev_mode,
            keystore_path=keystore_path,
            signer_uri=signer_uri,
            wallet_filepath=wallet_filepath,
            *args, **kwargs
        )

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

    @classmethod
    def address_from_filepath(cls, filepath: Path) -> str:
        """Extracts worker address by "peeking" inside the ursula configuration file."""
        operator_address = cls.peek(filepath=filepath, field='operator_address')
        if not is_checksum_address(operator_address):
            raise RuntimeError(f"Invalid checksum address detected in configuration file at '{filepath}'.")
        return operator_address

    def generate_runtime_filepaths(self, config_root: Path) -> dict:
        base_filepaths = super().generate_runtime_filepaths(config_root=config_root)
        filepaths = dict()
        base_filepaths.update(filepaths)
        return base_filepaths

    def generate_filepath(self, modifier: str = None, *args, **kwargs) -> Path:
        filepath = super().generate_filepath(modifier=modifier or self.keystore.id[:8], *args, **kwargs)
        return filepath

    def static_payload(self) -> dict:
        payload = dict(
            wallet_filepath=self._wallet_filepath,
            rest_host=self.rest_host,
            rest_port=self.rest_port,
            condition_blockchain_endpoints=self.condition_blockchain_endpoints,
        )
        return {**super().static_payload(), **payload}

    @property
    def dynamic_payload(self) -> dict:
        payload = dict(
            network_middleware=self.network_middleware,
            certificate=self.certificate,
            pre_payment_method=self.configure_pre_payment_method(),
            operator_address=self.wallet_address,
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
    SIGNER_ENVVAR = NUCYPHER_ENVVAR_ALICE_ETH_PASSWORD
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
            checksum_address=self.checksum_address,
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
    SIGNER_ENVVAR = NUCYPHER_ENVVAR_BOB_ETH_PASSWORD
    _CONFIG_FIELDS = (*CharacterConfiguration._CONFIG_FIELDS,)
