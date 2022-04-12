"""
This file is part of nucypher.

nucypher is free software: you can redistribute it and/or modify
it under the terms of the GNU Affero General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

nucypher is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU Affero General Public License for more details.

You should have received a copy of the GNU Affero General Public License
along with nucypher.  If not, see <https://www.gnu.org/licenses/>.
"""


import socket
import ssl
import time
from http import HTTPStatus
from pathlib import Path
from typing import Optional, Tuple
from typing import Sequence

import requests
from constant_sorrow.constants import EXEMPT_FROM_VERIFICATION
from cryptography import x509
from cryptography.hazmat.backends import default_backend
from cryptography.x509 import Certificate
from nucypher_core import MetadataRequest, FleetStateChecksum, NodeMetadata
from requests.exceptions import SSLError

from nucypher.blockchain.eth.registry import BaseContractRegistry
from nucypher.config.storages import ForgetfulNodeStorage
from nucypher.network.exceptions import NodeSeemsToBeDown
from nucypher.utilities.logging import Logger

SSL_LOGGER = Logger('ssl-middleware')
EXEMPT_FROM_VERIFICATION.bool_value(False)


class NucypherMiddlewareClient:
    library = requests
    timeout = 1.2

    def __init__(self,
                 registry: Optional['BaseContractRegistry'] = None,
                 eth_provider_uri: Optional[str] = None,
                 storage: Optional['NodeStorage'] = None,
                 *args, **kwargs):

        self.registry = registry
        self.eth_provider_uri = eth_provider_uri
        self.storage = storage or ForgetfulNodeStorage()  # for certificate storage

    def get_certificate(self,
                        host,
                        port,
                        timeout=4,
                        retry_attempts: int = 3,
                        retry_rate: int = 2,
                        current_attempt: int = 0):

        socket.setdefaulttimeout(timeout)  # Set Socket Timeout

        try:
            SSL_LOGGER.debug(f"Fetching {host}:{port} TLS certificate")
            certificate_pem = ssl.get_server_certificate(addr=(host, port))
            certificate = ssl.PEM_cert_to_DER_cert(certificate_pem)

        except socket.timeout:
            if current_attempt == retry_attempts:
                message = f"No Response from {host}:{port} after {retry_attempts} attempts"
                SSL_LOGGER.info(message)
                raise ConnectionRefusedError("No response from {}:{}".format(host, port))
            SSL_LOGGER.info(f"No Response from {host}:{port}. Retrying in {retry_rate} seconds...")
            time.sleep(retry_rate)
            return self.get_certificate(host, port, timeout, retry_attempts, retry_rate, current_attempt + 1)

        except OSError:
            raise  # TODO: #1835

        certificate = x509.load_der_x509_certificate(certificate, backend=default_backend())
        filepath = self.storage.store_node_certificate(certificate=certificate, port=port)
        return certificate, filepath

    @staticmethod
    def response_cleaner(response):
        return response

    def verify_and_parse_node_or_host_and_port(self, node_or_sprout, host, port):
        """
        Does two things:
        1) Verifies the node (unless it is EXEMPT_FROM_VERIFICATION, like when we initially get its certificate)
        2) Parses the node into a host and port, or returns the provided host and port.
        :return: A 3-tuple: host string, certificate, and the library to be used for the connection.
        """
        if node_or_sprout:
            if node_or_sprout is not EXEMPT_FROM_VERIFICATION:
                node = node_or_sprout.mature()  # Morph into a node.
                node.verify_node(network_middleware_client=self, registry=self.registry, eth_provider_uri=self.eth_provider_uri)
        return self.parse_node_or_host_and_port(node_or_sprout, host, port)

    def parse_node_or_host_and_port(self, node, host, port):
        if node:
            if any((host, port)):
                raise ValueError("Don't pass host and port if you are passing the node.")
            host, port = node.rest_interface.host, node.rest_interface.port
        elif not (host and port):
            raise ValueError("You need to pass either the node or a host and port.")
        return host, port, self.library

    def invoke_method(self, method, url, *args, **kwargs):
        self.clean_params(kwargs)
        if not kwargs.get("timeout"):
            if self.timeout:
                kwargs["timeout"] = self.timeout
        response = method(url, *args, **kwargs)
        return response

    def clean_params(self, request_kwargs):
        """
        No cleaning needed.
        """

    def node_information(self, host, port):
        # The only time a node is exempt from verification - when we are first getting its info.
        response = self.get(node_or_sprout=EXEMPT_FROM_VERIFICATION,
                            host=host, port=port,
                            path="public_information",
                            timeout=2)
        return response.content

    def __getattr__(self, method_name):
        # Quick sanity check.
        if method_name not in ("post", "get", "put", "patch", "delete"):
            raise TypeError(f"This client is for HTTP only - you need to use a real HTTP verb, not '{method_name}'.")

        def method_wrapper(path,
                           node_or_sprout=None,
                           host=None,
                           port=None,
                           *args, **kwargs):

            # Get interface
            host, port, http_client = self.verify_and_parse_node_or_host_and_port(node_or_sprout, host, port)
            endpoint = f"https://{host}:{port}/{path}"
            method = getattr(http_client, method_name)

            response = self._execute_method(node_or_sprout,
                                            host,
                                            port,
                                            method,
                                            endpoint,
                                            *args,
                                            **kwargs)
            # Handle response
            cleaned_response = self.response_cleaner(response)
            if cleaned_response.status_code >= 300:

                if cleaned_response.status_code == HTTPStatus.BAD_REQUEST:
                    raise RestMiddleware.BadRequest(reason=cleaned_response.json)

                elif cleaned_response.status_code == HTTPStatus.NOT_FOUND:
                    m = f"While trying to {method_name} {args} ({kwargs}), server 404'd.  Response: {cleaned_response.content}"
                    raise RestMiddleware.NotFound(m)

                elif cleaned_response.status_code == HTTPStatus.PAYMENT_REQUIRED:
                    # TODO: Use this as a hook to prompt Bob's payment for policy sponsorship
                    # https://getyarn.io/yarn-clip/ce0d37ba-4984-4210-9a40-c9c9859a3164
                    raise RestMiddleware.PaymentRequired(cleaned_response.content)

                elif cleaned_response.status_code == HTTPStatus.FORBIDDEN:
                    raise RestMiddleware.Unauthorized(cleaned_response.content)

                else:
                    raise RestMiddleware.UnexpectedResponse(cleaned_response.content, status=cleaned_response.status_code)

            return cleaned_response

        return method_wrapper

    def _execute_method(self,
                        node_or_sprout,
                        host,
                        port,
                        method,
                        endpoint,
                        *args, **kwargs):
        # Use existing cached SSL certificate or fetch fresh copy and retry
        cached_cert_filepath = Path(self.storage.generate_certificate_filepath(host=host, port=port))
        if cached_cert_filepath.exists():
            # already cached try it
            try:
                # Send request
                response = self.invoke_method(method, endpoint, verify=cached_cert_filepath,
                                              *args, **kwargs)

                # successful use of cached certificate
                return response
            except SSLError as e:
                # ignore this exception - probably means that our cached cert may not be up-to-date.
                SSL_LOGGER.debug(f"Cached cert for {host}:{port} is invalid {e}")

        # Fetch fresh copy of SSL certificate
        try:
            certificate, filepath = self.get_certificate(host=host, port=port)
        except NodeSeemsToBeDown as e:
            raise RestMiddleware.Unreachable(
                message=f'Node {node_or_sprout} {host}:{port} is unreachable: {e}')

        # Send request
        response = self.invoke_method(method, endpoint, verify=filepath,
                                      *args, **kwargs)
        return response

    def node_selector(self, node):
        return node.rest_url(), self.library

    def __len__(self):
        return 0  # Workaround so debuggers can represent objects of this class despite the unusual __getattr__.


class RestMiddleware:
    log = Logger()

    _client_class = NucypherMiddlewareClient

    class Unreachable(Exception):
        def __init__(self, message, *args, **kwargs):
            super().__init__(message, *args, **kwargs)

    class UnexpectedResponse(Exception):
        def __init__(self, message, status, *args, **kwargs):
            super().__init__(message, *args, **kwargs)
            self.status = status

    class NotFound(UnexpectedResponse):
        def __init__(self, *args, **kwargs):
            super().__init__(status=HTTPStatus.NOT_FOUND, *args, **kwargs)

    class BadRequest(UnexpectedResponse):
        def __init__(self, reason, *args, **kwargs):
            self.reason = reason
            super().__init__(message=reason, status=HTTPStatus.BAD_REQUEST, *args, **kwargs)

    class PaymentRequired(UnexpectedResponse):
        """Raised for HTTP 402"""
        def __init__(self, *args, **kwargs):
            super().__init__(status=HTTPStatus.PAYMENT_REQUIRED, *args, **kwargs)

    class Unauthorized(UnexpectedResponse):
        """Raised for HTTP 403"""
        def __init__(self, *args, **kwargs):
            super().__init__(status=HTTPStatus.FORBIDDEN, *args, **kwargs)

    def __init__(self, registry=None, eth_provider_uri: str = None):
        self.client = self._client_class(registry=registry, eth_provider_uri=eth_provider_uri)

    def request_revocation(self, ursula, revocation):
        # TODO: Implement offchain revocation #2787
        response = self.client.post(
            node_or_sprout=ursula,
            path=f"revoke",
            data=bytes(revocation),
        )
        return response

    def reencrypt(self, ursula: 'Ursula', reencryption_request_bytes: bytes):
        response = self.client.post(
            node_or_sprout=ursula,
            path=f"reencrypt",
            data=reencryption_request_bytes,
            timeout=2
        )
        return response

    def check_availability(self, initiator, responder):
        response = self.client.post(node_or_sprout=responder,
                                    data=bytes(initiator.metatada()),
                                    path="check_availability",
                                    timeout=6,  # Two round trips are expected
                                    )
        return response

    def ping(self, node):
        response = self.client.get(node_or_sprout=node, path="ping", timeout=2)
        return response

    def get_nodes_via_rest(self,
                           node,
                           fleet_state_checksum: FleetStateChecksum,
                           announce_nodes: Sequence[NodeMetadata]):

        request = MetadataRequest(fleet_state_checksum=fleet_state_checksum,
                                  announce_nodes=announce_nodes)
        response = self.client.post(node_or_sprout=node,
                                    path="node_metadata",
                                    data=bytes(request),
                                    )
        return response
