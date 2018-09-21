import os

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

    def _get_mock_client_by_port(self, port):  # TODO
        try:
            ursula = TEST_KNOWN_URSULAS_CACHE[port]
            rest_app = ursula.rest_app
            mock_client = TestClient(rest_app)
        except KeyError:
            raise RuntimeError(
                "Can't find an Ursula with port {} - did you spin up the right test ursulas?".format(port))
        return mock_client

    def consider_arrangement(self, arrangement=None):
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

    def node_information(self, host, port):
        mock_client = self._get_mock_client_by_port(port)
        response = mock_client.get("http://localhost/public_information")
        return response

    def get_nodes_via_rest(self, url, certificate_path, announce_nodes=None, nodes_i_need=None):

        mock_client = self._get_mock_client_by_url(url)

        if nodes_i_need:
            # TODO: This needs to actually do something.
            # Include node_ids in the request; if the teacher node doesn't know about the
            # nodes matching these ids, then it will ask other nodes.
            pass

        if announce_nodes:
            response = mock_client.post("https://{}/node_metadata".format(url),
                                        verify=False,
                                        data=bytes().join(bytes(n) for n in announce_nodes))  # TODO: TLS-only.
        else:
            response = mock_client.get("https://{}/node_metadata".format(url),
                                       verify=False)  # TODO: TLS-only.
        return response

    def put_treasure_map_on_node(self, node, map_id, map_payload):
        mock_client = self._get_mock_client_by_ursula(node)
        response = mock_client.post("http://localhost/treasure_map/{}".format(map_id),
                                    data=map_payload, verify=False)
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