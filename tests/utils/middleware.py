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
import time
import random
import os

import requests
import socket
from constant_sorrow.constants import CERTIFICATE_NOT_SAVED
from flask import Response

from nucypher.core import MetadataRequest

from nucypher.characters.lawful import Ursula
from nucypher.config.constants import TEMPORARY_DOMAIN
from nucypher.network.middleware import NucypherMiddlewareClient, RestMiddleware
from tests.utils.ursula import MOCK_KNOWN_URSULAS_CACHE


class BadTestUrsulas(RuntimeError):
    crash_right_now = True


class _TestMiddlewareClient(NucypherMiddlewareClient):
    timeout = None

    @staticmethod
    def response_cleaner(response):
        response.content = response.data
        return response

    def _get_mock_client_by_ursula(self, ursula):
        port = ursula.rest_interface.port
        return self._get_mock_client_by_port(port)

    def _get_mock_client_by_url(self, url):
        port = int(url.split(":")[1])
        return self._get_mock_client_by_port(port)

    def _get_mock_client_by_port(self, port):
        ursula = self._get_ursula_by_port(port)
        rest_app = ursula.rest_app
        rest_app.testing = True
        mock_client = rest_app.test_client()
        return mock_client

    def _get_ursula_by_port(self, port):
        mkuc = MOCK_KNOWN_URSULAS_CACHE
        try:
            return mkuc[port]
        except KeyError:
             raise BadTestUrsulas(
                "Can't find an Ursula with port {} - did you spin up the right test ursulas?".format(port))

    def parse_node_or_host_and_port(self, node=None, host=None, port=None):
        if node:
            if any((host, port)):
                raise ValueError("Don't pass host and port if you are passing the node.")
            mock_client = self._get_mock_client_by_ursula(node)
        elif all((host, port)):
            node = self._get_ursula_by_port(port)
            mock_client = self._get_mock_client_by_port(port)
        else:
            raise ValueError("You need to pass either the node or a host and port.")

        # We don't use certs in mock-style tests anyway.
        return node.rest_url(), CERTIFICATE_NOT_SAVED, mock_client

    def invoke_method(self, method, url, *args, **kwargs):
        _cert_location = kwargs.pop("verify")  # TODO: Is this something that can be meaningfully tested?
        kwargs.pop("timeout", None)  # Just get rid of timeout; not needed for the test client.
        response = super().invoke_method(method, url, *args, **kwargs)
        return response

    def clean_params(self, request_kwargs):
        request_kwargs["query_string"] = request_kwargs.pop("params", {})


class MockRestMiddleware(RestMiddleware):
    _ursulas = None

    _client_class = _TestMiddlewareClient

    class NotEnoughMockUrsulas(Ursula.NotEnoughUrsulas):
        pass

    def get_certificate(self, host, port, timeout=3, retry_attempts: int = 3, retry_rate: int = 2,
                        current_attempt: int = 0):
        ursula = self.client._get_ursula_by_port(port)
        return ursula.certificate


class MockRestMiddlewareForLargeFleetTests(MockRestMiddleware):
    """
    A MockRestMiddleware with workaround necessary to test the conditions that arise with thousands of nodes.
    """

    def get_nodes_via_rest(self,
                           node,
                           fleet_state_checksum,
                           announce_nodes=None):
        response_bytes = node.bytestring_of_known_nodes()
        r = Response(response_bytes)
        r.content = r.data
        return r


class SluggishLargeFleetMiddleware(MockRestMiddlewareForLargeFleetTests):
    """
    Similar to above, but with added delay to simulate network latency.
    """
    def put_treasure_map_on_node(self, node, *args, **kwargs):
        time.sleep(random.randrange(5, 15) / 100)
        result = super().put_treasure_map_on_node(node=node, *args, **kwargs)
        time.sleep(random.randrange(5, 15) / 100)
        return result


class _MiddlewareClientWithConnectionProblems(_TestMiddlewareClient):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.ports_that_are_down = set()
        self.certs_are_broken = False

    def _get_ursula_by_port(self, port):
        if port in self.ports_that_are_down:
            raise ConnectionRefusedError
        else:
            return super()._get_ursula_by_port(port)

    def get(self, *args, **kwargs):
        if kwargs.get("path") == "public_information":
            if self.certs_are_broken:
                raise requests.exceptions.SSLError
            port = kwargs.get("port")
            if port in self.ports_that_are_down:
                raise socket.gaierror

        real_get = super(_TestMiddlewareClient, self).__getattr__("get")
        return real_get(*args, **kwargs)


class NodeIsDownMiddleware(MockRestMiddleware):
    """
    Modified middleware to emulate one node being down amongst many.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.client = _MiddlewareClientWithConnectionProblems()

    def node_is_down(self, node):
        self.client.ports_that_are_down.add(node.rest_interface.port)

    def node_is_up(self, node):
        self.client.ports_that_are_down.remove(node.rest_interface.port)

    def all_nodes_up(self):
        self.client.ports_that_are_down = set()

    def all_nodes_down(self):
        self.client.ports_that_are_down = set(MOCK_KNOWN_URSULAS_CACHE)


class EvilMiddleWare(MockRestMiddleware):
    """
    Middleware for assholes.
    """

    def propagate_shitty_interface_id(self, ursula, shitty_metadata):
        """
        Try to get Ursula to propagate a malicious (or otherwise shitty) interface ID.
        """
        fleet_state_checksum = os.urandom(32).hex()
        request = MetadataRequest(fleet_state_checksum=fleet_state_checksum, announce_nodes=[shitty_metadata])
        response = self.client.post(node_or_sprout=ursula,
                                    path="node_metadata",
                                    data=bytes(request)
                                    )
        return response

    def upload_arbitrary_data(self, node, path, data):
        response = self.client.post(node_or_sprout=node,
                                    path=path,
                                    data=data)
        return response
