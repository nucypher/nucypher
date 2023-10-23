import socket
import time

import pytest
from requests import Session, RequestException

from nucypher.utilities.certs import (
    InMemoryCertAdapter,
    InMemoryCertSession,
    CertificateCache,
    Address
)

# Define test URLs
VALID_URL = "https://example.com"
INVALID_URL = "https://nonexistent-domain.com"

MOCK_CERT = """-----BEGIN CERTIFICATE-----
MIIDXTCCAkWgAwIBAgIJALm157+YvLEhMA0GCSqGSIb3DQEBCwUAMEUxCzAJBgNV
...
-----END CERTIFICATE-----"""


@pytest.fixture
def cache():
    return CertificateCache()


@pytest.fixture
def adapter(cache):
    _adapter = InMemoryCertAdapter()
    _adapter.cert_cache = cache
    return _adapter


@pytest.fixture
def session(adapter):
    s = InMemoryCertSession()
    s.adapter = adapter  # Use the same adapter instance
    return s


def test_init_adapter(cache, adapter):
    assert isinstance(adapter, InMemoryCertAdapter)


def test_cert_cache_set_get():
    cache = CertificateCache()
    address = Address('example.com', 443)
    cache.set(address, MOCK_CERT)
    assert cache.get(address) == MOCK_CERT


def test_cert_cache_expiry():
    cache = CertificateCache(cache_duration=1)
    address = Address('example.com', 443)
    cache.set(address, MOCK_CERT)
    assert not cache.is_expired(address)
    # Wait for the cert to expire
    time.sleep(2)
    assert cache.is_expired(address)


def test_cache_cert(cache):
    address = Address('example.com', 443)
    cache.set(address, 'cert_data')
    assert cache.get(address) == 'cert_data'


def test_send_request(session, mocker):
    mocker.patch.object(InMemoryCertAdapter, 'load_certificate')
    mocked_refresh = mocker.patch.object(session, '_refresh_certificate', return_value=MOCK_CERT)
    mocker.patch.object(Session, 'send', return_value='response')
    response = session.send(mocker.Mock(url=VALID_URL))
    mocked_refresh.assert_called()
    assert response == 'response'


def test_https_request_with_cert_caching():
    # Create a session with certificate caching
    session = InMemoryCertSession()

    # Send a request (it should succeed)
    response = session.get(VALID_URL)
    assert response.status_code == 200

    # Send another request to the same URL (it should use the cached certificate)
    response = session.get(VALID_URL)
    assert response.status_code == 200


def test_https_request_with_cert_refresh():
    # Create a session with certificate caching
    session = InMemoryCertSession()

    # Send a request (it should succeed)
    response = session.get(VALID_URL)
    assert response.status_code == 200

    # Manually expire the cached certificate
    hostname, port = InMemoryCertSession._parse_url(VALID_URL)
    session.cache._expirations[(hostname, port)] = 0

    # Send another request to the same URL (it should refresh the certificate)
    response = session.get(VALID_URL)
    assert response.status_code == 200


def test_fetch_server_cert_socket_error(session, mocker):
    mocker.patch('socket.create_connection', side_effect=socket.error)
    address = Address('localhost', 443)
    with pytest.raises(socket.error):
        session._refresh_certificate(address)


def test_send_request_exception(session, mocker):
    """Test that a RequestException is raised when the request fails."""
    mock_request = mocker.Mock()
    mock_request.url = 'https://localhost'

    mocker.patch.object(session, '_refresh_certificate', return_value=MOCK_CERT)
    mocker.patch('requests.Session.send', side_effect=RequestException)

    with pytest.raises(RequestException):
        session.send(mock_request)


def test_retry_on_request_exception(session, mocker):
    """Test to ensure that the request is retried upon encountering a RequestException."""
    mock_request = mocker.Mock()
    mock_request.url = 'https://localhost'

    mocker.patch.object(session, '_refresh_certificate', return_value=MOCK_CERT)
    mocker.patch('requests.Session.send', side_effect=[RequestException, 'response'])

    response = session.send(mock_request)
    assert response == 'response'
