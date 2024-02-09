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


def _replace_with_resolved_address(url: str, resolved_address: Address) -> str:
    """Replace the hostname in the URL with the provided IP address."""
    parsed_url = urlparse(url)
    components = list(parsed_url)
    # modify netloc entry
    components[1] = f"{resolved_address.hostname}:{resolved_address.port}"
    return urlunparse(tuple(components))


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


class SelfSignedPoolManager(PoolManager):
    def __init__(self, certificate_cache: CertificateCache, *args, **kwargs):
        self.certificate_cache = certificate_cache
        super().__init__(*args, **kwargs)

    def connection_from_url(self, url, pool_kwargs=None):
        if not pool_kwargs:
            pool_kwargs = {}
        ssl_context = pool_kwargs.get("ssl_context")
        if not ssl_context:
            ssl_context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
            ssl_context.verify_mode = ssl.CERT_REQUIRED
            ssl_context.check_hostname = False
            pool_kwargs["ssl_context"] = ssl_context

        parsed = urlparse(url)
        host, port = parsed.hostname, parsed.port
        cached_certificate = self.certificate_cache.get(Address(host, port))
        if cached_certificate:
            ssl_context.load_verify_locations(cadata=cached_certificate)

        return super().connection_from_url(url, pool_kwargs=pool_kwargs)


class SelfSignedCertificateAdapter(HTTPAdapter):
    """An adapter that verifies self-signed certificates in memory only."""

    log = logging.Logger(__name__)

    def __init__(self, certificate_cache: CertificateCache, *args, **kwargs):
        self.certificate_cache = certificate_cache
        super().__init__(*args, **kwargs)

    def init_poolmanager(self, *args, **kwargs) -> None:
        """Override the default poolmanager to use the certificate cache."""
        self.poolmanager = SelfSignedPoolManager(
            self.certificate_cache, *args, **kwargs
        )


class P2PSession(Session):
    _DEFAULT_HOSTNAME = ""
    _DEFAULT_PORT = 443

    def __init__(self):
        super().__init__()
        self.certificate_cache = CertificateCache()
        self.adapter = SelfSignedCertificateAdapter(self.certificate_cache)
        self.mount("https://", self.adapter)

    @classmethod
    def _resolve_address(cls, url) -> Address:
        """parse the URL and return the hostname and port as an Address named tuple."""
        parsed = urlparse(url)
        hostname = parsed.hostname or cls._DEFAULT_HOSTNAME
        hostname = gethostbyname(hostname)  # resolve DNS
        return Address(hostname, parsed.port or cls._DEFAULT_PORT)

    def __retry_send(self, address, request, *args, **kwargs) -> Response:
        self._refresh_certificate(address)
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
        self.__ensure_certificate_cached_and_uptodate(address)  # cache by resolved ip
        url = _replace_with_resolved_address(url=request.url, resolved_address=address)
        request.url = url  # replace the hostname with the resolved IP address
        try:
            return super().send(request, *args, **kwargs)
        except RequestException as e:
            self.adapter.log.debug(f"Request failed due to {e}, retrying...")
            return self.__retry_send(address, request, *args, **kwargs)

    def __ensure_certificate_cached_and_uptodate(self, address: Address) -> Certificate:
        if self.certificate_cache.should_cache_now(address):
            return self._refresh_certificate(address)
        certificate = self.certificate_cache.get(address)
        return certificate

    def _refresh_certificate(self, address: Address) -> Certificate:
        certificate = _fetch_server_cert(address)
        self.certificate_cache.set(address, certificate)
        return certificate
