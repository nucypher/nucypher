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
from apistar import TestClient

from nucypher.characters.lawful import Ursula
from nucypher.network.middleware import RestMiddleware
from nucypher.utilities.sandbox.constants import TEST_KNOWN_URSULAS_CACHE


class MockRestMiddleware(RestMiddleware):
    _ursulas = None

    class NotEnoughMockUrsulas(Ursula.NotEnoughUrsulas):
        pass

    def _get_mock_client_by_ursula(self, ursula):
        port = ursula.rest_information()[0].port
        return self._get_mock_client_by_port(port)

    def _get_mock_client_by_url(self, url):
        port = int(url.split(":")[1])
        return self._get_mock_client_by_port(port)

    def _get_mock_client_by_port(self, port):
        ursula = self._get_ursula_by_port(port)
        rest_app = ursula.rest_app
        mock_client = TestClient(rest_app)
        return mock_client

    def _get_ursula_by_port(self, port):
        try:
            return TEST_KNOWN_URSULAS_CACHE[port]
        except KeyError:
            raise RuntimeError(
                "Can't find an Ursula with port {} - did you spin up the right test ursulas?".format(port))

    def get_certificate(self, host, port, timeout=3, retry_attempts: int = 3,
                         retry_rate: int = 2, ):
        ursula = self._get_ursula_by_port(port)
        return ursula.certificate

    def consider_arrangement(self, arrangement):
        mock_client = self._get_mock_client_by_ursula(arrangement.ursula)
        response = mock_client.post("http://localhost/consider_arrangement", bytes(arrangement))
        assert response.status_code == 200
        return response

    def enact_policy(self, ursula, id, payload):
        mock_client = self._get_mock_client_by_ursula(ursula)
        response = mock_client.post('http://localhost/kFrag/{}'.format(id.hex()), payload)
        assert response.status_code == 200
        return True, ursula.stamp.as_umbral_pubkey()

    def send_work_order_payload_to_ursula(self, work_order):
        mock_client = self._get_mock_client_by_ursula(work_order.ursula)
        payload = work_order.payload()
        id_as_hex = work_order.arrangement_id.hex()
        return mock_client.post('http://localhost/kFrag/{}/reencrypt'.format(id_as_hex), payload)

    def get_treasure_map_from_node(self, node, map_id):
        mock_client = self._get_mock_client_by_ursula(node)
        return mock_client.get("http://localhost/treasure_map/{}".format(map_id))

    def node_information(self, host, port, certificate_filepath):
        mock_client = self._get_mock_client_by_port(port)
        response = mock_client.get("http://localhost/public_information")
        return response

    def get_nodes_via_rest(self, url, certificate_filepath, announce_nodes=None, nodes_i_need=None):

        mock_client = self._get_mock_client_by_url(url)

        if nodes_i_need:
            # TODO: This needs to actually do something.
            # Include node_ids in the request; if the teacher node doesn't know about the
            # nodes matching these ids, then it will ask other nodes.
            pass

        if announce_nodes:
            response = mock_client.post("https://{}/node_metadata".format(url),
                                        verify=certificate_filepath,
                                        data=bytes().join(bytes(n) for n in announce_nodes))
        else:
            response = mock_client.get("https://{}/node_metadata".format(url),
                                       verify=certificate_filepath)
        return response

    def put_treasure_map_on_node(self, node, map_id, map_payload):
        mock_client = self._get_mock_client_by_ursula(node)
        certificate_filepath = node.certificate_filepath

        response = mock_client.post("http://localhost/treasure_map/{}".format(map_id),
                                    data=map_payload, verify=certificate_filepath)
        return response

    def revoke_arrangement(self, ursula, revocation_notice):
        mock_client = self._get_mock_client_by_ursula(ursula)
        response = mock_client.post('http://localhost/kFrag/revoke', bytes(revocation_notice))
        
        if not response.status_code == 200:
            if response.status_code == 404:
                raise RuntimeError("KFrag doesn't exist to revoke with id {}".format(arrangement_id))
            raise RuntimeError("Bad response: {}".format(response.status_code))
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
                                    verify=False,
                                    data=bytes(shitty_interface_id))
        return response
