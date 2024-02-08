import ssl
import time
from typing import Dict, NamedTuple
from urllib.parse import urlparse, urlunparse

from _socket import gethostbyname
from requests import PreparedRequest, Response, Session
from requests.adapters import HTTPAdapter
from requests.exceptions import RequestException
from urllib3 import PoolManager

from nucypher.utilities import logging

Certificate = str


class Address(NamedTuple):
    hostname: str
    port: int


def _replace_hostname_with_ip(url: str, ip_address: str) -> str:
    """Replace the hostname in the URL with the provided IP address."""
    parsed_url = urlparse(url)
    return urlunparse(
        (
            parsed_url.scheme,
            f"{ip_address}:{parsed_url.port or ''}",
            parsed_url.path,
            parsed_url.params,
            parsed_url.query,
            parsed_url.fragment,
        )
    )


def _fetch_server_cert(address: Address) -> Certificate:
    """Fetch the server certificate from the given address."""
    certificate_pem = ssl.get_server_certificate(address)
    certificate = Certificate(certificate_pem)
    return certificate


class CertificateCache:
    """Cache for https certificates."""

    DEFAULT_DURATION = 3600  # seconds
    DEFAULT_REFRESH_INTERVAL = 600

    def __init__(
        self,
        cache_duration: int = DEFAULT_DURATION,
        refresh_interval: int = DEFAULT_REFRESH_INTERVAL,
    ):
        self._certificates: Dict[Address, Certificate] = dict()
        self._expirations: Dict[Address, float] = dict()
        self.cache_duration = cache_duration
        self.cache_refresh_interval = refresh_interval

    def get(self, address: Address) -> str:
        return self._certificates.get(address)

    def set(self, address: Address, certificate: Certificate) -> None:
        self._certificates[address] = certificate
        self._expirations[address] = time.time() + self.cache_duration

    def is_expired(self, address: Address) -> bool:
        return address in self._expirations and time.time() > self._expirations[address]

    def should_cache_now(self, address: Address) -> bool:
        return (
            address not in self._expirations
            or time.time() > self._expirations[address] - self.cache_refresh_interval
        )


class SelfSignedCertificateAdapter(HTTPAdapter):
    """An adapter that verifies self-signed certificates in memory only."""

    log = logging.Logger(__name__)

    def __init__(self, *args, **kwargs):
        self.ssl_context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        self.ssl_context.verify_mode = ssl.CERT_REQUIRED
        self.ssl_context.check_hostname = False
        super().__init__(*args, **kwargs)

    def init_poolmanager(self, *args, **kwargs) -> None:
        """Override the default poolmanager to use the  local SSL context."""
        self.poolmanager = PoolManager(*args, ssl_context=self.ssl_context, **kwargs)

    def trust_certificate(self, certificate: Certificate) -> None:
        """Accept the given certificate as trusted."""
        try:
            self.ssl_context.load_verify_locations(cadata=certificate)
        except ssl.SSLError as e:
            self.log.debug(f"Failed to load certificate {e}.")


class P2PSession(Session):
    _DEFAULT_HOSTNAME = ""
    _DEFAULT_PORT = 443

    def __init__(self):
        super().__init__()
        self.adapter = SelfSignedCertificateAdapter()
        self.cache = CertificateCache()
        self.mount("https://", self.adapter)

    @classmethod
    def _resolve_address(cls, url) -> Address:
        """parse the URL and return the hostname and port as an Address named tuple."""
        parsed = urlparse(url)
        hostname = parsed.hostname or cls._DEFAULT_HOSTNAME
        hostname = gethostbyname(hostname)  # resolve DNS
        return Address(hostname, parsed.port or cls._DEFAULT_PORT)

    def __retry_send(self, address, request, *args, **kwargs) -> Response:
        certificate = self._refresh_certificate(address)
        self.adapter.trust_certificate(certificate=certificate)
        try:
            return super().send(request, *args, **kwargs)
        except RequestException as e:
            self.adapter.log.debug(f"Request failed due to {e}, giving up.")
            raise

    def send(self, request: PreparedRequest, *args, **kwargs) -> Response:
        """
        Intercept the request, prefetch the host's certificate,
        and redirect the request to the certificate's resolved IP address.

        This embedded DNS resolution is necessary because the host's certificate
        may contain an IP address in the Subject Alternative Name (SAN) field,
        but the hostname in the URL may not resolve to the same IP address.
        """

        address = self._resolve_address(url=request.url)  # resolves dns
        certificate = self.__get_or_refresh_certificate(address)  # cache by resolved ip
        self.adapter.trust_certificate(certificate=certificate)
        url = _replace_hostname_with_ip(url=request.url, ip_address=address.hostname)
        request.url = url  # replace the hostname with the resolved IP address
        try:
            return super().send(request, *args, **kwargs)
        except RequestException as e:
            self.adapter.log.debug(f"Request failed due to {e}, retrying...")
            return self.__retry_send(address, request, *args, **kwargs)

    def __get_or_refresh_certificate(self, address: Address) -> Certificate:
        if self.cache.should_cache_now(address):
            return self._refresh_certificate(address)
        certificate = self.cache.get(address)
        return certificate

    def _refresh_certificate(self, address: Address) -> Certificate:
        certificate = _fetch_server_cert(address)
        self.cache.set(address, certificate)
        return certificate
