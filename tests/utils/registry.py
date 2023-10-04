from collections import defaultdict
from contextlib import contextmanager
from typing import List

from ape.contracts import ContractInstance
from eth_utils import to_checksum_address

from nucypher.blockchain.eth import domains
from nucypher.blockchain.eth.domains import (
    EthChain,
    PolygonChain,
    TACoDomain,
)
from nucypher.blockchain.eth.registry import (
    RegistryData,
    RegistrySource,
    RegistrySourceManager,
)
from nucypher.config.constants import TEMPORARY_DOMAIN


@contextmanager
def mock_registry_sources(mocker, domain_names: List[str] = None):
    if not domain_names:
        domain_names = [TEMPORARY_DOMAIN]

    supported_domains = []
    supported_domain_names = []
    for domain_name in domain_names:
        test_domain = TACoDomain(
            domain_name, EthChain.TESTERCHAIN, PolygonChain.TESTERCHAIN
        )
        supported_domains.append(test_domain)
        supported_domain_names.append(domain_name)

    mocker.patch.object(domains, "SUPPORTED_DOMAINS", supported_domains)
    mocker.patch.object(domains, "SUPPORTED_DOMAIN_NAMES", supported_domain_names)
    mocker.patch.object(MockRegistrySource, "ALLOWED_DOMAINS", domain_names)

    mocker.patch.object(RegistrySourceManager, "_FALLBACK_CHAIN", (MockRegistrySource,))

    yield  # run the test


class MockRegistrySource(RegistrySource):
    ALLOWED_DOMAINS = [TEMPORARY_DOMAIN]

    name = "Mock Registry Source"
    is_primary = False

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.domain not in self.ALLOWED_DOMAINS:
            raise ValueError(
                f"Somehow, MockRegistrySource is trying to get a registry for '{self.domain}'. "
                f"Only '{','.join(self.ALLOWED_DOMAINS)}' are supported.'"
            )

    @property
    def registry_name(self) -> str:
        return self.domain

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
        if self.domain != TEMPORARY_DOMAIN:
            raise ValueError(
                f"Somehow, ApeRegistrySource is trying to get a registry for '{self.domain}'. "
                f"Only '{TEMPORARY_DOMAIN}' is supported.'"
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
