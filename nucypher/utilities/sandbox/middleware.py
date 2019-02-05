"""
This file is part of nucypher.

nucypher is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

nucypher is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with nucypher.  If not, see <https://www.gnu.org/licenses/>.
"""
from bytestring_splitter import VariableLengthBytestring
from nucypher.characters.lawful import Ursula
from nucypher.network.middleware import RestMiddleware, NucypherMiddlewareClient
from nucypher.utilities.sandbox.constants import MOCK_KNOWN_URSULAS_CACHE


class _TestMiddlewareClient(NucypherMiddlewareClient):

    @staticmethod
    def response_cleaner(response):
        response.content = response.data
        return response

    def _get_mock_client_by_ursula(self, ursula):
        port = ursula.rest_information()[0].port
        return self._get_mock_client_by_port(port)

    def _get_mock_client_by_url(self, url):
        port = int(url.split(":")[1])
        return self._get_mock_client_by_port(port)

    def _get_ursula_by_port(self, port):
        try:
            return MOCK_KNOWN_URSULAS_CACHE[port]
        except KeyError:
            raise RuntimeError(
                "Can't find an Ursula with port {} - did you spin up the right test ursulas?".format(port))

    def parse_node_or_host_and_port(self, node, host, port):
        if node:
            if any((host, port)):
                raise ValueError("Don't pass host and port if you are passing the node.")
        elif all((host, port)):
            node = self._get_ursula_by_port(port)
        else:
            raise ValueError("You need to pass either the node or a host and port.")
        rest_app = node.rest_app
        rest_app.testing = True
        mock_client = rest_app.test_client()
        return node.rest_url(), node.certificate_filepath, mock_client

    def invoke_method(self, method, url, *args, **kwargs):
        cert_location = kwargs.pop("verify")  # TODO: Is this something that can be meaningfully tested?
        kwargs.pop("timeout", None)  # Just get rid of timeout; not needed for the test client.
        response = method(url, *args, **kwargs)
        return response


class MockRestMiddleware(RestMiddleware):
    _ursulas = None

    client = _TestMiddlewareClient()

    class NotEnoughMockUrsulas(Ursula.NotEnoughUrsulas):
        pass

    def get_certificate(self, host, port, timeout=3, retry_attempts: int = 3, retry_rate: int = 2,
                        current_attempt: int = 0):
        ursula = self._get_ursula_by_port(port)
        return ursula.certificate

    def consider_arrangement(self, arrangement):
        mock_client = self._get_mock_client_by_ursula(arrangement.ursula)
        response = mock_client.post("http://localhost/consider_arrangement",
                                    data=bytes(arrangement),
                                    content_type='application/octet')
        return response

    def enact_policy(self, ursula, id, payload):
        mock_client = self._get_mock_client_by_ursula(ursula)
        response = mock_client.post('http://localhost/kFrag/{}'.format(id.hex()), data=payload)
        return True, ursula.stamp.as_umbral_pubkey()

    def send_work_order_payload_to_ursula(self, work_order):
        mock_client = self._get_mock_client_by_ursula(work_order.ursula)
        payload = work_order.payload()
        id_as_hex = work_order.arrangement_id.hex()
        return mock_client.post('http://localhost/kFrag/{}/reencrypt'.format(id_as_hex), data=payload)

    def get_treasure_map_from_node(self, node, map_id):
        mock_client = self._get_mock_client_by_ursula(node)
        response = mock_client.get("http://localhost/treasure_map/{}".format(map_id))
        return response

    def get_nodes_via_rest(self, url, *args, **kwargs):
        response = super().get_nodes_via_rest(url, client=self._get_mock_client_by_url(url), *args, **kwargs)
        return response

    def put_treasure_map_on_node(self, node, map_id, map_payload):
        mock_client = self._get_mock_client_by_ursula(node)
        response = mock_client.post("http://localhost/treasure_map/{}".format(map_id),
                                    data=map_payload)
        return response

    def revoke_arrangement(self, ursula, revocation):
        mock_client = self._get_mock_client_by_ursula(ursula)
        response = mock_client.delete('http://localhost/kFrag/{}'.format(
            revocation.arrangement_id.hex()),
            data=bytes(revocation))
        return response


class EvilMiddleWare(MockRestMiddleware):
    """
    Middleware for assholes.
    """

    def propagate_shitty_interface_id(self, ursula, shitty_interface_id):
        """
        Try to get Ursula to propagate a malicious (or otherwise shitty) interface ID.
        """
        mock_client = self._get_mock_client_by_ursula(ursula)
        response = mock_client.post("http://localhost/node_metadata".format(mock_client),
                                    data=bytes(VariableLengthBytestring(shitty_interface_id))
                                    )
        return response
