from ipaddress import IPv4Address

import pytest
from flask import Request

from nucypher.utilities.networking import (
    LOOPBACK_ADDRESS,
    _ip_sources,
    _resolve_ipv4,
    get_global_source_ipv4,
)


@pytest.fixture
def mock_request_factory(mocker):
    def _mock_request_factory(headers=None, remote_addr=None):
        request = mocker.MagicMock(spec=Request)
        request.remote_addr = remote_addr or LOOPBACK_ADDRESS
        request.headers = headers or {}
        return request

    return _mock_request_factory


def test_resolve_ipv4_with_valid_ipv4():
    assert _resolve_ipv4("8.8.8.8") == IPv4Address("8.8.8.8")


def test_resolve_ipv4_with_valid_mapped_ipv6():
    assert _resolve_ipv4("::ffff:8.8.8.8") == IPv4Address("8.8.8.8")


def test_resolve_ipv4_with_non_mapped_ipv6():
    assert _resolve_ipv4("2001:0db8::") is None


def test_ip_sources_with_both_headers(mock_request_factory):
    request = mock_request_factory(
        headers={"X-Forwarded-For": "8.8.8.8", "X-Real-IP": "1.1.1.1"}
    )
    ips = list(_ip_sources(request))
    assert ips == ["8.8.8.8", "1.1.1.1", LOOPBACK_ADDRESS]


def test_ip_sources_with_real_ip_header(mock_request_factory):
    request = mock_request_factory(headers={"X-Real-IP": "1.1.1.1"})
    ips = list(_ip_sources(request))
    assert ips == ["1.1.1.1", LOOPBACK_ADDRESS]


def test_ip_sources_with_no_headers_but_remote_addr(mock_request_factory):
    request = mock_request_factory(remote_addr="203.0.113.100")
    ips = list(_ip_sources(request))
    assert ips == ["203.0.113.100"]


def test_get_request_global_ipv4_with_forwarded_ip(mock_request_factory):
    request = mock_request_factory(headers={"X-Forwarded-For": "8.8.8.8, 192.168.1.1"})
    assert get_global_source_ipv4(request) == "8.8.8.8"
    assert isinstance(get_global_source_ipv4(request), str)


def test_get_request_global_ipv4_with_private_ip_only(mock_request_factory):
    request = mock_request_factory(headers={"X-Forwarded-For": "192.168.1.1"})
    assert get_global_source_ipv4(request) is None


def test_get_request_global_ipv4_with_no_headers_but_valid_remote_addr(
    mock_request_factory,
):
    request = mock_request_factory(remote_addr="8.8.8.8")
    assert get_global_source_ipv4(request) == "8.8.8.8"
    assert isinstance(get_global_source_ipv4(request), str)


def test_get_request_global_ipv4_with_invalid_remote_addr(mock_request_factory):
    request = mock_request_factory(remote_addr="not_an_ip")
    with pytest.raises(
        ValueError, match="'not_an_ip' does not appear to be an IPv4 or IPv6 address"
    ):
        get_global_source_ipv4(request)
