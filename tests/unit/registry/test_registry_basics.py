import pytest

from nucypher.blockchain.eth.registry import ContractRegistry
from nucypher.config.constants import TEMPORARY_DOMAIN_NAME
from tests.constants import TESTERCHAIN_CHAIN_ID, TEMPORARY_DOMAIN
from tests.utils.registry import MockRegistrySource


@pytest.fixture(scope="function")
def name():
    return "TestContract"


@pytest.fixture(scope="function")
def address():
    return "0xdeadbeef"


@pytest.fixture(scope="function")
def abi():
    return ["fake", "data"]


@pytest.fixture(scope="function")
def record(name, address, abi):
    record_data = {name: {"address": address, "abi": abi}}
    return record_data


@pytest.fixture(scope="function")
def data(record):
    _data = {TESTERCHAIN_CHAIN_ID: record}
    return _data


@pytest.fixture(scope="function")
def source(data):
    source = MockRegistrySource(domain=TEMPORARY_DOMAIN)
    source.data = data
    return source


@pytest.fixture(scope="function")
def registry(record, source):
    registry = ContractRegistry(source=source)
    return registry


def test_registry_id_consistency(registry, source):
    new_registry = ContractRegistry(source=source)
    new_registry._data = registry._data
    assert new_registry.id == registry.id


def test_registry_name_search(registry, name, address, abi):
    record = registry.search(chain_id=TESTERCHAIN_CHAIN_ID, contract_name=name)
    assert len(record) == 4, "Registry record is the wrong length"
    assert record.chain_id == TESTERCHAIN_CHAIN_ID
    assert record.name == name
    assert record.address == address
    assert record.abi == abi


def test_registry_address_search(registry, name, address, abi):
    record = registry.search(chain_id=TESTERCHAIN_CHAIN_ID, contract_address=address)
    assert len(record) == 4, "Registry record is the wrong length"
    assert record.chain_id == TESTERCHAIN_CHAIN_ID
    assert record.name == name
    assert record.address == address
    assert record.abi == abi


def test_local_registry_unknown_contract_name_search(registry):
    with pytest.raises(ContractRegistry.UnknownContract):
        registry.search(
            chain_id=TESTERCHAIN_CHAIN_ID, contract_name="this does not exist"
        )


def test_local_contract_registry_ambiguous_search_terms(data, name, record, address):
    data[TESTERCHAIN_CHAIN_ID]["fakeContract"] = record[name]
    source = MockRegistrySource(domain=TEMPORARY_DOMAIN)
    source.data = data
    registry = ContractRegistry(source=source)
    with pytest.raises(ContractRegistry.AmbiguousSearchTerms):
        registry.search(chain_id=TESTERCHAIN_CHAIN_ID, contract_address=address)
