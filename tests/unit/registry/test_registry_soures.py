import json

import pytest
import requests
from requests import Response

from nucypher.blockchain.eth import domains
from nucypher.blockchain.eth.registry import (
    EmbeddedRegistrySource,
    GithubRegistrySource,
    LocalRegistrySource,
    RegistrySource,
    RegistrySourceManager,
)
from nucypher.config.constants import TEMPORARY_DOMAIN_NAME
from tests.constants import TEMPORARY_DOMAIN


@pytest.fixture(scope="function")
def registry_data():
    _registry_data = {
        "2958363635247": {
            "TestContract": {"address": "0xdeadbeef", "abi": ["fake", "data"]},
            "AnotherTestContract": {"address": "0xdeadbeef", "abi": ["fake", "data"]},
        },
        "393742274944474": {
            "YetAnotherContract": {"address": "0xdeadbeef", "abi": ["fake", "data"]}
        },
    }
    return _registry_data


@pytest.fixture(scope="function")
def mock_200_response(mocker, registry_data):
    mock_response = Response()
    mock_response.status_code = 200
    mock_response._content = json.dumps(registry_data).encode("utf-8")
    mocker.patch.object(requests, "get", return_value=mock_response)


@pytest.fixture(scope="function")
def test_registry_filepath(tmpdir, registry_data):
    filepath = tmpdir.join("registry.json")
    with open(filepath, "w") as f:
        json.dump(registry_data, f)
    yield filepath
    filepath.remove()


@pytest.mark.usefixtures("mock_200_response")
def test_github_registry_source(registry_data):
    source = GithubRegistrySource(domain=TEMPORARY_DOMAIN)
    assert source.domain.name == TEMPORARY_DOMAIN_NAME
    assert str(source.domain) == TEMPORARY_DOMAIN_NAME
    assert bytes(source.domain) == TEMPORARY_DOMAIN_NAME.encode("utf-8")
    data = source.get()
    assert data == registry_data
    assert source.data == registry_data
    assert data == source.data


@pytest.mark.skip("Skip until contract registry updated to use amoy instead of mumbai")
@pytest.mark.parametrize("domain", list(domains.SUPPORTED_DOMAINS.values()))
def test_get_actual_github_registry_file(domain):
    source = GithubRegistrySource(domain=domain)
    assert str(domain.eth_chain.id) in source.data
    assert str(domain.polygon_chain.id) in source.data


def test_local_registry_source(registry_data, test_registry_filepath):
    source = LocalRegistrySource(
        filepath=test_registry_filepath, domain=TEMPORARY_DOMAIN
    )
    assert source.domain.name == TEMPORARY_DOMAIN_NAME
    assert str(source.domain) == TEMPORARY_DOMAIN_NAME
    assert bytes(source.domain) == TEMPORARY_DOMAIN_NAME.encode("utf-8")
    data = source.get()
    assert data == registry_data
    assert source.data == registry_data
    assert data == source.data


def test_embedded_registry_source(registry_data, test_registry_filepath, mocker):
    mocker.patch.object(
        EmbeddedRegistrySource,
        "get_publication_endpoint",
        return_value=test_registry_filepath,
    )
    source = EmbeddedRegistrySource(domain=TEMPORARY_DOMAIN)
    assert source.domain.name == TEMPORARY_DOMAIN_NAME
    assert str(source.domain) == TEMPORARY_DOMAIN_NAME
    assert bytes(source.domain) == TEMPORARY_DOMAIN_NAME.encode("utf-8")
    data = source.get()
    assert data == registry_data
    assert source.data == registry_data
    assert data == source.data


def test_registry_source_manager_fallback(
    registry_data, test_registry_filepath, mocker
):
    github_source_get = mocker.patch.object(
        GithubRegistrySource, "get", side_effect=RegistrySource.Unavailable
    )
    mocker.patch.object(
        EmbeddedRegistrySource,
        "get_publication_endpoint",
        return_value=test_registry_filepath,
    )
    embedded_source_get = mocker.spy(EmbeddedRegistrySource, "get")
    RegistrySourceManager._FALLBACK_CHAIN = (
        GithubRegistrySource,
        EmbeddedRegistrySource,
    )
    source_manager = RegistrySourceManager(domain=TEMPORARY_DOMAIN)
    assert source_manager.domain.name == TEMPORARY_DOMAIN_NAME
    assert str(source_manager.domain) == TEMPORARY_DOMAIN_NAME
    assert bytes(source_manager.domain) == TEMPORARY_DOMAIN_NAME.encode("utf-8")

    primary_sources = source_manager.get_primary_sources()
    assert len(primary_sources) == 1
    assert primary_sources[0] == GithubRegistrySource

    source = source_manager.fetch_latest_publication()
    github_source_get.assert_called_once()
    embedded_source_get.assert_called_once()
    assert source.data == registry_data
    assert isinstance(source, EmbeddedRegistrySource)

    mocker.patch.object(
        EmbeddedRegistrySource,
        "get_publication_endpoint",
        side_effect=RegistrySource.Unavailable,
    )

    with pytest.raises(RegistrySourceManager.NoSourcesAvailable):
        source_manager.fetch_latest_publication()
