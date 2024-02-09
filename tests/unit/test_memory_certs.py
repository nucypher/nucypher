import socket
import time

import pytest
from requests import RequestException, Session

from nucypher.utilities.certs import (
    Address,
    CertificateCache,
    P2PSession,
    SelfSignedCertificateAdapter,
)

# Define test URLs
VALID_URL = "https://lynx.nucypher.network:9151/status"
INVALID_URL = "https://nonexistent-domain.com"

MOCK_CERT = """-----BEGIN CERTIFICATE-----
MIIDXTCCAkWgAwIBAgIJALm157+YvLEhMA0GCSqGSIb3DQEBCwUAMEUxCzAJBgNV
...
-----END CERTIFICATE-----"""

VALID_BUT_INCORRECT_CERT_FOR_VALID_URL = """-----BEGIN CERTIFICATE-----
MIIBgzCCAQigAwIBAgIUYZMjb9wgSIv0G3H9zP6Xezi3y6kwCgYIKoZIzj0EAwQw
GDEWMBQGA1UEAwwNMTg4LjE2Ni4yNy40NjAeFw0yNDAxMzAxMjQ0MzhaFw0yNTAx
MjkxMjQ0MzhaMBgxFjAUBgNVBAMMDTE4OC4xNjYuMjcuNDYwdjAQBgcqhkjOPQIB
BgUrgQQAIgNiAASnd+YYrbrV3WW/hb1+4+RRD/lWLkcgKM5JjZLjuwNU/Ndr1vEl
qOAwbz+fcdwgJ7SAkSoK2fQOt90NnnBPDA12MCc0ScwyiQxS7Cm382B4h3No4M4Z
E3bLLn1u69g9Y26jEzARMA8GA1UdEQQIMAaHBLymGy4wCgYIKoZIzj0EAwQDaQAw
ZgIxAL4cpbec9Hs8O4uXB8zESJJ32err5jejFhWOFexppRTNjhM5copO9c8x24zJ
IzqeQgIxALCe9ynrDkT/tOtBNjvPiNvR8aosRsgdsQCcbk3fUCsYXSXTuphpDgMf
IKaHuG9nuw==
-----END CERTIFICATE-----
"""


@pytest.fixture
def cache():
    return CertificateCache()


@pytest.fixture
def adapter(cache):
    _adapter = SelfSignedCertificateAdapter(certificate_cache=cache)
    return _adapter


@pytest.fixture
def session(adapter):
    s = P2PSession()
    s.adapter = adapter  # Use the same adapter instance
    return s


def test_init_adapter(cache, adapter):
    assert isinstance(adapter, SelfSignedCertificateAdapter)


def test_cert_cache_set_get():
    cache = CertificateCache()
    address = Address("example.com", 443)
    cache.set(address, MOCK_CERT)
    assert cache.get(address) == MOCK_CERT


def test_cert_cache_expiry():
    cache = CertificateCache(cache_duration=1)
    address = Address("example.com", 443)
    cache.set(address, MOCK_CERT)
    assert not cache.is_expired(address)
    # Wait for the cert to expire
    time.sleep(2)
    assert cache.is_expired(address)


def test_cache_cert(cache):
    address = Address("example.com", 443)
    cache.set(address, "cert_data")
    assert cache.get(address) == "cert_data"


def test_send_request(session, mocker):
    mocked_refresh = mocker.patch.object(
        session, "_refresh_certificate", return_value=MOCK_CERT
    )
    mocker.patch.object(Session, "send", return_value="response")
    response = session.send(mocker.Mock(url=VALID_URL))
    mocked_refresh.assert_called()
    assert response == "response"


def test_https_request_with_cert_caching():
    # Create a session with certificate caching
    session = P2PSession()

    # Send a request (it should succeed)
    response = session.get(VALID_URL)
    assert response.status_code == 200

    # Send another request to the same URL (it should use the cached certificate)
    response = session.get(VALID_URL)
    assert response.status_code == 200


def test_https_request_with_cert_refresh():
    # Create a session with certificate caching
    session = P2PSession()

    # Send a request (it should succeed)
    response = session.get(VALID_URL)
    assert response.status_code == 200

    # Manually expire the cached certificate
    hostname, port = P2PSession._resolve_address(VALID_URL)
    session.cache._expirations[(hostname, port)] = 0

    # Send another request to the same URL (it should refresh the certificate)
    response = session.get(VALID_URL)
    assert response.status_code == 200


def test_https_request_with_invalid_cached_cert_and_refresh():
    # Create a session with certificate caching
    session = P2PSession()
    hostname, port = P2PSession._resolve_address(VALID_URL)

    session.cache.set(Address(hostname, port), VALID_BUT_INCORRECT_CERT_FOR_VALID_URL)

    # Send a request (it should succeed after retrying and refreshing cert)
    response = session.get(VALID_URL)
    assert response.status_code == 200


def test_fetch_server_cert_socket_error(session, mocker):
    mocker.patch("socket.create_connection", side_effect=socket.error)
    address = Address("localhost", 443)
    with pytest.raises(socket.error):
        session._refresh_certificate(address)


def test_send_request_exception(session, mocker):
    """Test that a RequestException is raised when the request fails."""
    mock_request = mocker.Mock()
    mock_request.url = "https://localhost"

    mocker.patch.object(session, "_refresh_certificate", return_value=MOCK_CERT)
    mocker.patch("requests.Session.send", side_effect=RequestException)

    with pytest.raises(RequestException):
        session.send(mock_request)


def test_retry_on_request_exception(session, mocker):
    """Test to ensure that the request is retried upon encountering a RequestException."""
    mock_request = mocker.Mock()
    mock_request.url = "https://localhost"

    mocker.patch.object(session, "_refresh_certificate", return_value=MOCK_CERT)
    mocker.patch("requests.Session.send", side_effect=[RequestException, "response"])

    response = session.send(mock_request)
    assert response == "response"
