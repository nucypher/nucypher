import socket
import ssl
from _socket import gethostbyname
from typing import NamedTuple, Dict
from urllib.parse import urlparse, urlunparse

import time
from cryptography import x509
from cryptography.hazmat.backends import default_backend
from requests import Session, Response, PreparedRequest
from requests.adapters import HTTPAdapter
from requests.exceptions import RequestException
from urllib3 import PoolManager

from nucypher.crypto.tls import _read_tls_certificate
from nucypher.utilities import logging

Certificate = str


class Address(NamedTuple):
    hostname: str
    port: int


class CertificateCache:

    DEFAULT_DURATION = 3600
    DEFAULT_REFRESH_INTERVAL = 600

    def __init__(
            self,
            cache_duration: int = DEFAULT_DURATION,
            refresh_interval: int = DEFAULT_REFRESH_INTERVAL
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
        return (address in self._expirations
                and time.time() > self._expirations[address])

    def should_cache_now(self, address: Address) -> bool:
        return (
                address not in self._expirations
                or time.time()
                > self._expirations[address]
                - self.cache_refresh_interval
        )


class InMemoryCertAdapter(HTTPAdapter):
    log = logging.Logger(__name__)

    def __init__(self, *args, **kwargs):
        self.ssl_context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        self.ssl_context.verify_mode = ssl.CERT_REQUIRED  # Enforce certificate verification
        self.ssl_context.check_hostname = False  # Disable hostname checking
        super().__init__(*args, **kwargs)

    def init_poolmanager(self, *args, **kwargs) -> None:
        self.poolmanager = PoolManager(*args, ssl_context=self.ssl_context, **kwargs)

    def accept_certificate(self, certificate: Certificate) -> None:
        try:
            self.ssl_context.load_verify_locations(cadata=certificate)
        except ssl.SSLError as e:
            self.log.debug(f"Failed to load certificate {e}.")


class InMemoryCertSession(Session):

    _DEFAULT_HOSTNAME = ''
    _DEFAULT_PORT = 443

    def __init__(self):
        super().__init__()
        self.adapter = InMemoryCertAdapter()
        self.cache = CertificateCache()
        self.mount("https://", self.adapter)

    @classmethod
    def _parse_url(cls, url) -> Address:
        parsed = urlparse(url)
        return Address(
            parsed.hostname or cls._DEFAULT_HOSTNAME,
            parsed.port or cls._DEFAULT_PORT
        )

    def __retry_send(self, address, request, *args, **kwargs) -> Response:
        certificate = self._refresh_certificate(address)
        self.adapter.accept_certificate(certificate=certificate)
        try:
            return super().send(request, *args, **kwargs)
        except RequestException as e:
            self.adapter.log.debug(f"Request failed due to {e}, giving up.")
            raise

    def extract_ip_from_certificate(self, certificate_pem: str) -> str:
        """
        Extract IP address from the Subject Alternative Name (SAN) field of the certificate.
        """
        certificate = x509.load_pem_x509_certificate(certificate_pem.encode(), default_backend())
        try:
            san = certificate.extensions.get_extension_for_class(x509.SubjectAlternativeName)
        except x509.ExtensionNotFound:
            raise ValueError("No SAN extension found in certificate")

        # Check if an IP address is listed in SAN and return the first one
        for ip in san.value.get_values_for_type(x509.IPAddress):
            return str(ip)

    def replace_hostname_with_ip(self, url: str, ip_address: str) -> str:
        """
        Replace the hostname in the URL with the provided IP address.
        """
        parsed_url = urlparse(url)
        # Reconstruct the URL with the IP address instead of the hostname
        return urlunparse((
            parsed_url.scheme,
            f"{ip_address}:{parsed_url.port}",
            parsed_url.path,
            parsed_url.params,
            parsed_url.query,
            parsed_url.fragment
        ))

    def send(self, request: PreparedRequest, *args, **kwargs) -> Response:
        address = self._parse_url(url=request.url)
        certificate = self.get_or_refresh_certificate(address)
        self.adapter.accept_certificate(certificate=certificate)
        url = self.replace_hostname_with_ip(
            url=request.url,
            ip_address=gethostbyname(address.hostname)
        )
        request.url = url
        try:
            return super().send(request, *args, **kwargs)
        except RequestException as e:
            self.adapter.log.debug(f"Request failed due to {e}, retrying...")
            return self.__retry_send(address, request, *args, **kwargs)

    def get_or_refresh_certificate(self, address: Address) -> Certificate:
        if self.cache.should_cache_now(address):
            return self._refresh_certificate(address)
        certificate = self.cache.get(address)
        return certificate

    def _refresh_certificate(self, address: Address) -> Certificate:
        certificate = self.__fetch_server_cert(address)
        self.cache.set(address, certificate)
        return certificate

    @staticmethod
    def __fetch_server_cert(address: Address) -> Certificate:
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE

        with socket.create_connection(address) as sock:
            with context.wrap_socket(sock, server_hostname=address.hostname) as ssock:
                sock.close()  # close the insecure socket
                certificate_bin = ssock.getpeercert(binary_form=True)

        certificate = Certificate(ssl.DER_cert_to_PEM_cert(certificate_bin))
        return certificate
