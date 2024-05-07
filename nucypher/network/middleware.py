import os
from http import HTTPStatus
from typing import Optional, Sequence, Tuple, Union

from constant_sorrow.constants import EXEMPT_FROM_VERIFICATION
from nucypher_core import FleetStateChecksum, MetadataRequest, NodeMetadata

from nucypher import characters
from nucypher.blockchain.eth.registry import ContractRegistry
from nucypher.utilities.certs import P2PSession
from nucypher.utilities.logging import Logger

SSL_LOGGER = Logger("ssl-middleware")
EXEMPT_FROM_VERIFICATION.bool_value(False)

# It’s a good practice to set connect timeouts to slightly larger
# than a multiple of 3, which is the default TCP packet retransmission window.
# (https://requests.readthedocs.io/en/latest/user/advanced/#timeouts)
MIDDLEWARE_DEFAULT_CONNECT_TIMEOUT = os.getenv(
    "NUCYPHER_MIDDLEWARE_DEFAULT_CONNECT_TIMEOUT", default=3.05
)

MIDDLEWARE_DEFAULT_CERTIFICATE_TIMEOUT = os.getenv(
    "MIDDLEWARE_DEFAULT_CERTIFICATE_TIMEOUT", default=4
)


class NucypherMiddlewareClient:
    library = P2PSession()
    timeout = MIDDLEWARE_DEFAULT_CONNECT_TIMEOUT

    def __init__(
        self,
        eth_endpoint: Optional[str],
        registry: Optional[ContractRegistry] = None,
        *args,
        **kwargs,
    ):
        if not eth_endpoint:
            raise ValueError("eth_endpoint is required for NucypherMiddlewareClient")

        self.registry = registry
        self.eth_endpoint = eth_endpoint

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
                node.verify_node(
                    network_middleware_client=self,
                    registry=self.registry,
                    eth_endpoint=self.eth_endpoint,
                )
        return self.parse_node_or_host_and_port(node_or_sprout, host, port)

    def parse_node_or_host_and_port(self, node, host, port):
        if node:
            if any((host, port)):
                raise ValueError(
                    "Don't pass host and port if you are passing the node."
                )
            host, port = node.rest_interface.host, node.rest_interface.port
        elif not (host and port):
            raise ValueError("You need to pass either the node or a host and port.")
        return host, port, self.library

    def _determine_timeout(
        self, caller_provided_timeout: Optional[float] = None
    ) -> Union[float, Tuple[float, float]]:
        # Basically there are two timeouts for the `requests` library:
        # - `connect timeout`: number of seconds Requests will wait for your client to establish
        #                      a connection to a remote machine
        # - `read timeout`: number of seconds the client will wait for the server to send a response
        #
        # If one timeout value is provided to `requests`, then the same value is used
        # for both timeouts.
        # When someone provides a timeout via the method call, they are really intending
        # to specify the `read timeout`, so we use our own internal connect timeout
        # but keep caller provided timeout as a backup since connect timeout can be overridden by
        # subclasses and potentially set to None eg. tests).
        connect_timeout = self.timeout or caller_provided_timeout
        read_timeout = caller_provided_timeout or self.timeout
        if connect_timeout == read_timeout:
            return connect_timeout
        else:
            return connect_timeout, read_timeout

    def invoke_method(self, method, url, *args, **kwargs):
        self.clean_params(kwargs)

        timeout = self._determine_timeout(kwargs.get("timeout"))
        kwargs["timeout"] = timeout

        response = method(url, *args, **kwargs)
        return response

    def clean_params(self, request_kwargs):
        """
        No cleaning needed.
        """

    def node_information(self, host, port):
        # The only time a node is exempt from verification - when we are first getting its info.
        response = self.get(
            node_or_sprout=EXEMPT_FROM_VERIFICATION,
            host=host,
            port=port,
            path="public_information",
            timeout=2,
        )
        return response.content

    def __getattr__(self, method_name):
        # Quick sanity check.
        if method_name not in ("post", "get", "put", "patch", "delete"):
            raise TypeError(
                f"This client is for HTTP only - you need to use a real HTTP verb, not '{method_name}'."
            )

        def method_wrapper(
            path, node_or_sprout=None, host=None, port=None, *args, **kwargs
        ):
            # Get interface
            host, port, http_client = self.verify_and_parse_node_or_host_and_port(
                node_or_sprout, host, port
            )
            endpoint = f"https://{host}:{port}/{path}"
            method = getattr(http_client, method_name)
            response = self._execute_method(method, endpoint, *args, **kwargs)

            # Handle response
            cleaned_response = self.response_cleaner(response)
            if cleaned_response.status_code >= 300:
                if cleaned_response.status_code == HTTPStatus.BAD_REQUEST:
                    raise RestMiddleware.BadRequest(reason=cleaned_response.text)

                elif cleaned_response.status_code == HTTPStatus.NOT_FOUND:
                    m = f"While trying to {method_name} {args} ({kwargs}), server 404'd.  Response: {cleaned_response.text}"
                    raise RestMiddleware.NotFound(m)

                elif cleaned_response.status_code == HTTPStatus.PAYMENT_REQUIRED:
                    # TODO: Use this as a hook to prompt Bob's payment for policy sponsorship
                    # https://getyarn.io/yarn-clip/ce0d37ba-4984-4210-9a40-c9c9859a3164
                    raise RestMiddleware.PaymentRequired(cleaned_response.text)

                elif cleaned_response.status_code == HTTPStatus.FORBIDDEN:
                    raise RestMiddleware.Unauthorized(cleaned_response.text)

                else:
                    raise RestMiddleware.UnexpectedResponse(
                        cleaned_response.text, status=cleaned_response.status_code
                    )

            return cleaned_response

        return method_wrapper

    def _execute_method(self, method, endpoint, *args, **kwargs):
        # Send request
        response = self.invoke_method(method, endpoint, *args, **kwargs)
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
        """Based for all HTTP status codes"""

        def __init__(self, message, status, *args, **kwargs):
            super().__init__(message, *args, **kwargs)
            self.status = status

    class NotFound(UnexpectedResponse):
        """Raised for HTTP 404"""

        def __init__(self, *args, **kwargs):
            super().__init__(status=HTTPStatus.NOT_FOUND, *args, **kwargs)

    class BadRequest(UnexpectedResponse):
        """Raised for HTTP 400"""

        def __init__(self, reason, *args, **kwargs):
            self.reason = reason
            super().__init__(
                message=reason, status=HTTPStatus.BAD_REQUEST, *args, **kwargs
            )

    class PaymentRequired(UnexpectedResponse):
        """Raised for HTTP 402"""

        def __init__(self, *args, **kwargs):
            super().__init__(status=HTTPStatus.PAYMENT_REQUIRED, *args, **kwargs)

    class Unauthorized(UnexpectedResponse):
        """Raised for HTTP 403"""

        def __init__(self, *args, **kwargs):
            super().__init__(status=HTTPStatus.FORBIDDEN, *args, **kwargs)

    def __init__(self, eth_endpoint: str, registry=None):
        self.client = self._client_class(registry=registry, eth_endpoint=eth_endpoint)

    def reencrypt(
        self,
        ursula: "characters.lawful.Ursula",
        reencryption_request_bytes: bytes,
        timeout: int,
    ):
        response = self.client.post(
            node_or_sprout=ursula,
            path="reencrypt",
            data=reencryption_request_bytes,
            timeout=timeout,
        )
        return response

    def get_encrypted_decryption_share(
        self,
        ursula: "characters.lawful.Ursula",
        decryption_request_bytes: bytes,
        timeout: int,
    ):
        response = self.client.post(
            node_or_sprout=ursula,
            path="decrypt",
            data=decryption_request_bytes,
            timeout=timeout,
        )
        return response

    def ping(self, node):
        response = self.client.get(node_or_sprout=node, path="ping")
        return response

    def get_nodes_via_rest(
        self,
        node,
        fleet_state_checksum: FleetStateChecksum,
        announce_nodes: Sequence[NodeMetadata],
    ):
        request = MetadataRequest(
            fleet_state_checksum=fleet_state_checksum, announce_nodes=announce_nodes
        )
        response = self.client.post(
            node_or_sprout=node,
            path="node_metadata",
            data=bytes(request),
        )
        return response
