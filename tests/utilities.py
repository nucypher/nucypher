import asyncio
import random
from collections import OrderedDict
from typing import List, Set

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
constants.NUMBER_OF_URSULAS_IN_NETWORK(10)

_ALL_URSULAS = {}


def make_ursulas(ether_addresses: list, ursula_starting_port: int,
                 miner_agent=None, miners=False, bare=False) -> Set[Ursula]:
    """
    :param ether_addresses: Ethereum addresses to create ursulas with.
    :param ursula_starting_port: The port of the first created Ursula; subsequent Ursulas will increment the port number by 1.


    :param miner_agent: A miner agent instance to use when creating ursulas.
    :param miners: If True, create staking ursulas on the blockchain from the addresses
    :param bare: If True, Create an non-learning Ursula without a rest app, dht server or database attached,
                 for testing mining functionality when network transport is not needed. "Just a miner"

    :return: A list of created Ursulas
    """

    event_loop = asyncio.get_event_loop()

    ursulas = set()
    for port, ether_address in enumerate(ether_addresses, start=ursula_starting_port):

        if bare:
            ursula = Ursula(is_me=False,            # do not attach dht server
                            rest_host="127.0.0.1",  # TODO: remove rest interface
                            rest_port=port + 100,
                            checksum_address=ether_address,
                            always_be_learning=False,
                            miner_agent=miner_agent,
                            abort_on_learning_error=True)

            ursula.is_me = True  # Patch to allow execution of transacting methods in tests

        else:
            federated_only = not miners
            if federated_only:
                ether_address = None
            ursula = Ursula(is_me=True,
                            checksum_address=ether_address,
                            dht_host="127.0.0.1",
                            dht_port=port,
                            db_name="test-{}".format(port),
                            rest_host="127.0.0.1",
                            rest_port=port+100,
                            always_be_learning=False,
                            miner_agent=miner_agent,
                            federated_only=federated_only)

            ursula.attach_rest_server()

            class MockDatastoreThreadPool(object):
                def callInThread(self, f, *args, **kwargs):
                    return f(*args, **kwargs)

            ursula.datastore_threadpool = MockDatastoreThreadPool()
            ursula.dht_listen()

            for ursula_to_teach in ursulas:
                # Add other Ursulas as known nodes.
                for ursula_to_learn_about in ursulas:
                    ursula_to_teach.remember_node(ursula_to_learn_about)

                event_loop.run_until_complete(
                    ursula.dht_server.bootstrap(
                        [("127.0.0.1", ursula_starting_port + _c) for _c in range(len(ursulas))]))
                ursula.publish_dht_information()

        if miners is True:
            # TODO: 309
            # stake a random amount
            min_stake, balance = constants.MIN_ALLOWED_LOCKED, ursula.token_balance
            amount = random.randint(min_stake, balance)

            # for a random lock duration
            min_locktime, max_locktime = constants.MIN_LOCKED_PERIODS, constants.MAX_MINTING_PERIODS
            periods = random.randint(min_locktime, max_locktime)

            ursula.stake(amount=amount, lock_periods=periods)
        else:
            ursula.federated_only = True

        ursulas.add(ursula)
        _ALL_URSULAS[ursula.rest_interface.port] = ursula

    return ursulas


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

        for ursula in self.alice._known_nodes:
            arrangement = MockArrangement(alice=self.alice, ursula=ursula,
                                          expiration=expiration)

            self.consider_arrangement(network_middleware=network_middleware, arrangement=arrangement)


class MockRestMiddleware(RestMiddleware):

    _ursulas = None

    class NotEnoughMockUrsulas(MinerAgent.NotEnoughMiners):
        pass

    def __get_mock_client_by_port(self, port):  # TODO
        try:
            ursula = _ALL_URSULAS[port]
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

    def enact_policy(self, ursula, id, payload):
        mock_client = self.__get_mock_client_by_port(ursula.rest_interface.port)
        response = mock_client.post('http://localhost/kFrag/{}'.format(id.hex()), payload)
        assert response.status_code == 200
        return True, ursula.stamp.as_umbral_pubkey()

    def send_work_order_payload_to_ursula(self, work_order):
        mock_client = self.__get_mock_client_by_port(work_order.ursula.rest_interface.port)
        payload = work_order.payload()
        id_as_hex = work_order.arrangement_id.hex()
        return mock_client.post('http://localhost/kFrag/{}/reencrypt'.format(id_as_hex), payload)

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
