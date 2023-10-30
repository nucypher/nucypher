from collections import defaultdict
from contextlib import contextmanager
from typing import List

from ape.contracts import ContractInstance
from eth_utils import to_checksum_address

from nucypher.blockchain.eth.domains import TACoDomain
from nucypher.blockchain.eth.registry import (
    RegistryData,
    RegistrySource,
    RegistrySourceManager,
)
from nucypher.config.constants import TEMPORARY_DOMAIN_NAME
from tests.constants import TEMPORARY_DOMAIN


@contextmanager
def mock_registry_sources(mocker, _domains: List[TACoDomain] = None):
    if not _domains:
        _domains = [TEMPORARY_DOMAIN]
    _supported_domains = mocker.patch.dict(
        "nucypher.blockchain.eth.domains.SUPPORTED_DOMAINS",
        {str(domain): domain for domain in _domains},
    )
    mocker.patch.object(MockRegistrySource, "ALLOWED_DOMAINS", list(map(str, _domains)))
    mocker.patch.object(RegistrySourceManager, "_FALLBACK_CHAIN", (MockRegistrySource,))
    yield


class MockRegistrySource(RegistrySource):
    ALLOWED_DOMAINS = [TEMPORARY_DOMAIN_NAME]

    name = "Mock Registry Source"
    is_primary = False

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if str(self.domain) not in self.ALLOWED_DOMAINS:
            raise ValueError(
                f"Somehow, MockRegistrySource is trying to get a registry for '{self.domain}'. "
                f"Only '{','.join(self.ALLOWED_DOMAINS)}' are supported.'"
            )

    @property
    def registry_name(self) -> str:
        return str(self.domain)

    def get_publication_endpoint(self) -> str:
        return f":mock-registry-source:/{self.registry_name}"

    def get(self) -> RegistryData:
        self.logger.debug(f"Reading registry at {self.get_publication_endpoint()}")
        data = dict()
        return data


class ApeRegistrySource(RegistrySource):
    name = "Ape Registry Source"
    is_primary = False

    _DEPLOYMENTS = None

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if str(self.domain) != TEMPORARY_DOMAIN_NAME:
            raise ValueError(
                f"Somehow, ApeRegistrySource is trying to get a registry for '{self.domain}'. "
                f"Only '{TEMPORARY_DOMAIN_NAME}' is supported.'"
            )
        if self._DEPLOYMENTS is None:
            raise ValueError(
                "ApeRegistrySource has not been initialized with deployments."
            )

    @classmethod
    def set_deployments(cls, deployments: List[ContractInstance]):
        cls._DEPLOYMENTS = deployments

    def get_publication_endpoint(self) -> str:
        return "ape"

    def get(self) -> RegistryData:
        data = defaultdict(dict)
        for contract_instance in self._DEPLOYMENTS:
            entry = {
                "address": to_checksum_address(contract_instance.address),
                "abi": [abi.dict() for abi in contract_instance.contract_type.abi],
            }
            chain_id = contract_instance.chain_manager.chain_id
            contract_name = contract_instance.contract_type.name
            data[chain_id][contract_name] = entry
        return data
