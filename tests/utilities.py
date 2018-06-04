import asyncio
from typing import List

from apistar.test import TestClient

from nucypher.characters import Ursula
from nucypher.config.configs import NucypherConfiguration
from nucypher.network.middleware import NetworkMiddleware
from nucypher.policy.models import ArrangementResponse
from constant_sorrow import constants


#
# Setup
#

EVENT_LOOP = asyncio.get_event_loop()
asyncio.set_event_loop(EVENT_LOOP)

constants.URSULA_PORT(7468)
constants.NUMBER_OF_URSULAS_IN_NETWORK(6)


def make_ursulas(ether_addresses: list, ursula_starting_port: int, config: NucypherConfiguration) -> List[Ursula]:
    """
    :param how_many_ursulas: How many Ursulas to create.
    :param ursula_starting_port: The port of the first created Ursula; subsequent Ursulas will increment the port number by 1.
    :return: A list of created Ursulas
    """
    event_loop = asyncio.get_event_loop()

    _ursulas = []
    for _counter, ether_address in enumerate(ether_addresses):
        port = ursula_starting_port + _counter
        ursula = Ursula(ether_address=ether_address, dht_port=port, db_name="test-{}".format(port),
                        ip_address="127.0.0.1", rest_port=port+100, config=config)

        class MockDatastoreThreadPool(object):
            def callInThread(self, f, *args, **kwargs):
                return f(*args, **kwargs)

        ursula.datastore_threadpool = MockDatastoreThreadPool()
        ursula.dht_listen()

        _ursulas.append(ursula)

    for ursula in _ursulas:
        event_loop.run_until_complete(
            ursula.dht_server.bootstrap([("127.0.0.1", ursula_starting_port+_c) for _c in range(len(_ursulas))]))
        ursula.publish_dht_information()

    return _ursulas


class MockArrangementResponse(ArrangementResponse):
    was_accepted = True

    def __bytes__(self):
        return b"This is a arrangement response; we have no idea what the bytes repr will be."


class MockNetworkMiddleware(NetworkMiddleware):

    def __init__(self, ursulas):
        self._ursulas = {bytes(u.stamp): u for u in ursulas}
        self.ursulas = iter(ursulas)

    def consider_arrangement(self, arrangement=None):
        try:
            ursula = next(self.ursulas)
        except StopIteration:
            raise self.NotEnoughQualifiedUrsulas
        mock_client = TestClient(ursula.rest_app)
        response = mock_client.post("http://localhost/consider_arrangement", bytes(arrangement))
        assert response.status_code == 200
        return ursula, MockArrangementResponse()

    def enact_policy(self, ursula, hrac, payload):
        rest_app = self._get_rest_app_by_port(ursula.rest_port)
        mock_client = TestClient(rest_app)
        response = mock_client.post('http://localhost/kFrag/{}'.format(hrac.hex()), payload)
        assert response.status_code == 200
        return True, ursula.stamp.as_umbral_pubkey()

    def _get_rest_app_by_port(self, port):
        for ursula in self._ursulas.values():
            if ursula.rest_port == port:
                rest_app = ursula.rest_app
                break
        else:
            raise RuntimeError(
                "Can't find an Ursula with port {} - did you spin up the right test ursulas?".format(port))
        return rest_app

    def send_work_order_payload_to_ursula(self, work_order):
        rest_app = self._get_rest_app_by_port(work_order.ursula.rest_port)
        mock_client = TestClient(rest_app)
        payload = work_order.payload()
        hrac_as_hex = work_order.kfrag_hrac.hex()
        return mock_client.post('http://localhost/kFrag/{}/reencrypt'.format(hrac_as_hex), payload)

    def get_treasure_map_from_node(self, node, map_id):
        rest_app = self._get_rest_app_by_port(node.rest_port)
        mock_client = TestClient(rest_app)
        return mock_client.get("http://localhost/treasure_map/{}".format(map_id.hex()))

    def ursula_from_rest_interface(self, address, port):
        rest_app = self._get_rest_app_by_port(port)
        mock_client = TestClient(rest_app)
        response = mock_client.get("http://localhost/public_keys")
        return response

    def get_nodes_via_rest(self, address, port):
        rest_app = self._get_rest_app_by_port(port)
        mock_client = TestClient(rest_app)
        response = mock_client.get("http://localhost/list_nodes")
        return response

    def push_treasure_map_to_node(self, node, map_id, map_payload):
        rest_app = self._get_rest_app_by_port(node.rest_port)
        mock_client = TestClient(rest_app)
        response = mock_client.post("http://localhost/treasure_map/{}".format(map_id.hex()),
                      data=map_payload, verify=False)
        return response
