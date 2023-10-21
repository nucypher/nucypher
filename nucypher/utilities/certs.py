import socket
import ssl
from urllib.parse import urlparse

from requests import Session
from requests.adapters import HTTPAdapter
from urllib3.poolmanager import PoolManager


class InMemoryCertAdapter(HTTPAdapter):
    def __init__(self, *args, **kwargs):
        self.ssl_context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        super().__init__(*args, **kwargs)

    def init_poolmanager(self, *args, **kwargs):
        self.poolmanager = PoolManager(*args, ssl_context=self.ssl_context, **kwargs)

    def update_cert(self, cert_pem):
        self.ssl_context.load_verify_locations(cadata=cert_pem)


class InMemoryCertSession(Session):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.adapter = InMemoryCertAdapter()
        self.mount("https://", self.adapter)

    def send(self, *args, **kwargs):
        # Parse the URL to extract hostname and port
        url = kwargs.get('url', args[0].url)
        parsed = urlparse(url)
        hostname = parsed.hostname or ''
        port = parsed.port or 443

        # Fetch and update the certificate
        cert_pem = self.fetch_server_cert(hostname, port)
        self.adapter.update_cert(cert_pem)

        # Perform the actual request
        return super().send(*args, **kwargs)

    @staticmethod
    def fetch_server_cert(hostname, port):
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE

        with socket.create_connection((hostname, port)) as sock:
            with context.wrap_socket(sock, server_hostname=hostname) as ssock:
                cert_bin = ssock.getpeercert(True)
        cert_pem = ssl.DER_cert_to_PEM_cert(cert_bin)
        return cert_pem

