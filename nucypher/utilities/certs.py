import socket
import ssl
from typing import Tuple
from urllib.parse import urlparse

import time
from requests import Session, Response
from requests.adapters import HTTPAdapter
from requests.exceptions import RequestException
from urllib3.poolmanager import PoolManager


def parse_url(url) -> Tuple[str, int]:
    parsed = urlparse(url)
    hostname = parsed.hostname or ''
    port = parsed.port or 443
    return hostname, port


class InMemoryCertAdapter(HTTPAdapter):
    """Transport adapter that uses a cached certificate for HTTPS requests"""

    def __init__(
            self,
            cache_duration: int = 3600,
            refresh_interval: int = 600,
            *args, **kwargs
    ):
        self.ssl_context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        self.cert_cache = {}
        self.cache_expiry = {}
        self.cache_duration = cache_duration
        self.cache_refresh_interval = refresh_interval
        super().__init__(*args, **kwargs)

    def init_poolmanager(self, *args, **kwargs) -> None:
        """Override the default poolmanager to use the local SSL context"""
        self.poolmanager = PoolManager(*args, ssl_context=self.ssl_context, **kwargs)

    def set_active_cert(self, cert_pem: str) -> None:
        """Set the active certificate for the SSL context"""
        self.ssl_context.load_verify_locations(cadata=cert_pem)

    def get_cached_cert(self, hostname: str, port: int) -> str:
        return self.cert_cache.get((hostname, port))

    def set_cached_cert(self, hostname: str, port: int, cert_pem: str) -> None:
        self.cert_cache[(hostname, port)] = cert_pem
        self.cache_expiry[(hostname, port)] = time.time() + self.cache_duration

    def is_cert_expired(self, hostname: str, port: int) -> bool:
        return ((hostname, port) in self.cache_expiry
                and time.time() > self.cache_expiry[(hostname, port)])

    def should_cache_now(self, hostname: str, port: int) -> bool:
        return (
                (hostname, port) not in self.cache_expiry
                or time.time()
                > self.cache_expiry[(hostname, port)]
                - self.cache_refresh_interval
        )


class InMemoryCertSession(Session):

    def __init__(self):
        super().__init__()
        self.adapter = InMemoryCertAdapter()
        self.mount("https://", self.adapter)

    def send(self, *args, **kwargs) -> Response:
        """
        Override the send to check if the certificate should be refreshed
        and to refresh it if needed before sending the request.
        """

        # Parse the URL to extract hostname and port
        url = kwargs.get('url', args[0].url)
        hostname, port = parse_url(url=url)

        if self.adapter.should_cache_now(hostname=hostname, port=port):
            self.refresh_certificate(hostname=hostname, port=port)

        try:
            # Perform the actual request
            response = super().send(*args, **kwargs)
        except RequestException:
            # reconnect and retry once
            self.refresh_certificate(hostname=hostname, port=port)
            response = super().send(*args, **kwargs)

        return response

    def refresh_certificate(self, hostname: str, port: int) -> None:
        cert_pem = self.__fetch_server_cert(hostname, port)
        self.adapter.set_cached_cert(
            hostname=hostname,
            port=port,
            cert_pem=cert_pem
        )

    @staticmethod
    def __fetch_server_cert(hostname: str, port: int) -> str:
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE

        with socket.create_connection((hostname, port)) as sock:
            with context.wrap_socket(sock, server_hostname=hostname) as wrapped_sock:
                cert_bin = wrapped_sock.getpeercert(binary_form=True)
        cert_pem = ssl.DER_cert_to_PEM_cert(cert_bin)
        return cert_pem
