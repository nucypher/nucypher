import asyncio
import random
from collections import OrderedDict
from typing import List

import maya
from apistar.test import TestClient
from constant_sorrow import constants

from nucypher.blockchain.eth.agents import MinerAgent
from nucypher.characters import Ursula
#
# Setup
#
from nucypher.network.middleware import RestMiddleware
from nucypher.policy.models import Arrangement, Policy

TEST_EVENT_LOOP = asyncio.get_event_loop()
asyncio.set_event_loop(TEST_EVENT_LOOP)

constants.URSULA_PORT_SEED(7468)
constants.NUMBER_OF_URSULAS_IN_NETWORK(6)


def make_ursulas(ether_addresses: list, ursula_starting_port: int, miners=False) -> List[Ursula]:
    """
    :param how_many_ursulas: How many Ursulas to create.
    :param ursula_starting_port: The port of the first created Ursula; subsequent Ursulas will increment the port number by 1.
    :return: A list of created Ursulas
    """
    event_loop = asyncio.get_event_loop()

    _ursulas = []
    for _counter, ether_address in enumerate(ether_addresses):
        port = ursula_starting_port + _counter
        ursula = Ursula(is_me=True, ether_address=ether_address, dht_port=port, db_name="test-{}".format(port),
                        ip_address="127.0.0.1", rest_port=port + 100)

        class MockDatastoreThreadPool(object):
            def callInThread(self, f, *args, **kwargs):
                return f(*args, **kwargs)

        ursula.datastore_threadpool = MockDatastoreThreadPool()
        ursula.dht_listen()

        _ursulas.append(ursula)

    for ursula in _ursulas:
        event_loop.run_until_complete(
            ursula.dht_server.bootstrap([("127.0.0.1", ursula_starting_port + _c) for _c in range(len(_ursulas))]))
        ursula.publish_dht_information()

    return _ursulas


class MockArrangement(Arrangement):
    _arrangements = OrderedDict()

    def publish(self) -> None:
        self._arrangements[self.id()] = self

    def revoke(self):
        del self._arrangements[self.id()]


class MockPolicy(Policy):
    def make_arrangements(self, network_middleware, quantity: int,
                          deposit: int, expiration: maya.MayaDT, ursulas: List[Ursula]=None) -> None:
        """
        Create and consider n Arangement objects from all known nodes.
        """

        for ursula in self.alice.known_nodes:
            arrangement = MockArrangement(alice=self.alice, ursula=ursula,
                                          hrac=self.hrac(),
                                          expiration=expiration)

            self.consider_arrangement(network_middleware=network_middleware, arrangement=arrangement)


class MockRestMiddleware(RestMiddleware):

    _ursulas = None

    class NotEnoughMockUrsulas(MinerAgent.NotEnoughMiners):
        pass

    def __get_local_rest_app_by_port(self, port):  # TODO
        for ursula in self._ursulas:
            if ursula.rest_port == port:
                rest_app = ursula.rest_app
                break
        else:
            raise RuntimeError(
                "Can't find an Ursula with port {} - did you spin up the right test ursulas_on_network?".format(port))
        return rest_app

    def consider_arrangement(self, ursula, arrangement=None):
        mock_client = TestClient(ursula.rest_app)
        response = mock_client.post("http://localhost/consider_arrangement", bytes(arrangement))
        assert response.status_code == 200
        return ursula, True  # TODO: ursula always accepts!

    def enact_policy(self, ursula, hrac, payload):
        mock_client = TestClient(ursula.rest_app)
        response = mock_client.post('http://localhost/kFrag/{}'.format(hrac.hex()), payload)
        assert response.status_code == 200
        return True, ursula.stamp.as_umbral_pubkey()

    def send_work_order_payload_to_ursula(self, work_order):
        mock_client = TestClient(work_order.ursula.rest_app)
        payload = work_order.payload()
        hrac_as_hex = work_order.kfrag_hrac.hex()
        return mock_client.post('http://localhost/kFrag/{}/reencrypt'.format(hrac_as_hex), payload)

    def get_treasure_map_from_node(self, node, map_id):
        mock_client = TestClient(node.rest_app)
        return mock_client.get("http://localhost/treasure_map/{}".format(map_id.hex()))

    def ursula_from_rest_interface(self, address, port):
        rest_app = self.__get_local_rest_app_by_port(port)
        mock_client = TestClient(rest_app)
        response = mock_client.get("http://localhost/public_keys")
        return response

    def get_nodes_via_rest(self, address, port):
        rest_app = self.__get_local_rest_app_by_port(port)
        mock_client = TestClient(rest_app)
        response = mock_client.get("http://localhost/list_nodes")
        return response

    def push_treasure_map_to_node(self, node, map_id, map_payload):
        mock_client = TestClient(node.rest_app)
        response = mock_client.post("http://localhost/treasure_map/{}".format(map_id.hex()),
                      data=map_payload, verify=False)
        return response
