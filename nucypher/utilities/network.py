import asyncio
from collections.__init__ import OrderedDict
from typing import List

import maya
from apistar import TestClient
from constant_sorrow import constants

from nucypher.blockchain.eth.agents import MinerAgent
from nucypher.characters import Ursula
from nucypher.network.middleware import RestMiddleware
from nucypher.policy.models import Arrangement, Policy
from nucypher.utilities.blockchain import _TEST_KNOWN_URSULAS_CACHE
#
# Setup
#

TEST_EVENT_LOOP = asyncio.get_event_loop()
asyncio.set_event_loop(TEST_EVENT_LOOP)

constants.URSULA_PORT_SEED(7468)
constants.NUMBER_OF_URSULAS_IN_NETWORK(10)


class MockRestMiddleware(RestMiddleware):

    _ursulas = None

    class NotEnoughMockUrsulas(MinerAgent.NotEnoughMiners):
        pass

    def __get_mock_client_by_port(self, port):  # TODO
        try:
            ursula = _TEST_KNOWN_URSULAS_CACHE[port]
            rest_app = ursula.rest_app
            mock_client = TestClient(rest_app)
        except KeyError:
            raise RuntimeError(
                "Can't find an Ursula with port {} - did you spin up the right test ursulas?".format(port))
        return mock_client

    def consider_arrangement(self, arrangement=None):
        mock_client = self.__get_mock_client_by_port(arrangement.ursula.rest_interface.port)
        response = mock_client.post("http://localhost/consider_arrangement", bytes(arrangement))
        assert response.status_code == 200
        return response

    def enact_policy(self, ursula, hrac, payload):
        mock_client = self.__get_mock_client_by_port(ursula.rest_interface.port)
        response = mock_client.post('http://localhost/kFrag/{}'.format(hrac.hex()), payload)
        assert response.status_code == 200
        return True, ursula.stamp.as_umbral_pubkey()

    def send_work_order_payload_to_ursula(self, work_order):
        mock_client = self.__get_mock_client_by_port(work_order.ursula.rest_interface.port)
        payload = work_order.payload()
        hrac_as_hex = work_order.kfrag_hrac.hex()
        return mock_client.post('http://localhost/kFrag/{}/reencrypt'.format(hrac_as_hex), payload)

    def get_treasure_map_from_node(self, node, map_id):
        mock_client = self.__get_mock_client_by_port(node.rest_interface.port)
        return mock_client.get("http://localhost/treasure_map/{}".format(map_id))

    def node_information(self, host, port):
        mock_client = self.__get_mock_client_by_port(port)
        response = mock_client.get("http://localhost/public_information")
        return response

    def get_nodes_via_rest(self, address, port, node_ids):
        mock_client = self.__get_mock_client_by_port(port)
        # TODO: Better passage of node IDs here.
        # if node_ids:
        #     node_address_bytestring = bytes().join(bytes(id) for id in node_ids)
        #     params = {'nodes': node_address_bytestring}
        # else:
        #     params = None
        response = mock_client.get("http://localhost/list_nodes")
        return response

    def put_treasure_map_on_node(self, node, map_id, map_payload):
        mock_client = self.__get_mock_client_by_port(node.rest_interface.port)
        response = mock_client.post("http://localhost/treasure_map/{}".format(map_id),
                      data=map_payload, verify=False)
        return response


class MockArrangement(Arrangement):
    _arrangements = OrderedDict()

    def publish(self) -> None:
        self._arrangements[self.id()] = self

    def revoke(self):
        del self._arrangements[self.id()]


class MockPolicy(Policy):
    def make_arrangements(self, network_middleware,
                          deposit: int,
                          expiration: maya.MayaDT,
                          ursulas: List[Ursula]=None) -> None:

        """
        Create and consider n Arangement objects from all known nodes.
        """

        for ursula in self.alice._known_nodes:
            arrangement = MockArrangement(alice=self.alice, ursula=ursula,
                                          hrac=self.hrac(),
                                          expiration=expiration)

            self.consider_arrangement(network_middleware=network_middleware, arrangement=arrangement)