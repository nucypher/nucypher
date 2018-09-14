import asyncio
import maya
import random
from typing import List, Set

from apistar import TestClient
from collections.__init__ import OrderedDict
from constant_sorrow import constants
from eth_utils import to_checksum_address
from nucypher.blockchain.eth.agents import MinerAgent
from nucypher.characters import Ursula
from nucypher.crypto.api import secure_random
from nucypher.network.middleware import RestMiddleware
from nucypher.policy.models import Arrangement, Policy
from umbral.keys import UmbralPrivateKey
from web3 import Web3


#
# Test Utility Constants
#

_TEST_KNOWN_URSULAS_CACHE = {}


#
# Event Loop Setup
#

TEST_EVENT_LOOP = asyncio.get_event_loop()
asyncio.set_event_loop(TEST_EVENT_LOOP)

constants.URSULA_PORT_SEED(7468)
constants.NUMBER_OF_URSULAS_IN_NETWORK(10)


#
# Test Utility Functions
#

def make_ursulas(ether_addresses: list,
                 miner_agent=None,
                 miners=False,
                 bare=False,
                 know_each_other=True,
                 **ursula_kwargs) -> Set[Ursula]:
    """
    :param ether_addresses: Ethereum addresses to create ursulas with.
    :param ursula_starting_port: The port of the first created Ursula; subsequent Ursulas will increment the port number by 1.


    :param miner_agent: A miner agent instance to use when creating ursulas.
    :param miners: If True, create staking ursulas on the blockchain from the addresses
    :param bare: If True, Create an non-learning Ursula without a rest app, dht server or database attached,
                 for testing mining functionality when network transport is not needed. "Just a miner"

    :return: A list of created Ursulas
    """

    if isinstance(ether_addresses, int):
        ether_addresses = [to_checksum_address(secure_random(20)) for _ in range(ether_addresses)]

    event_loop = asyncio.get_event_loop()
    if not _TEST_KNOWN_URSULAS_CACHE:
        starting_port = constants.URSULA_PORT_SEED
    else:
        starting_port = max(_TEST_KNOWN_URSULAS_CACHE.keys()) + 1

    ursulas = set()
    for port, ether_address in enumerate(ether_addresses, start=starting_port):

        if bare:
            ursula = Ursula(is_me=False,            # do not attach dht server
                            rest_host="localhost",  # TODO: remove rest interface
                            rest_port=port + 100,
                            checksum_address=ether_address,
                            always_be_learning=False,
                            miner_agent=miner_agent,
                            abort_on_learning_error=True,
                            **ursula_kwargs)

            ursula.is_me = True  # Patch to allow execution of transacting methods in tests

        else:
            federated_only = not miners
            if federated_only:
                ether_address = None
            ursula = Ursula(is_me=True,
                            checksum_address=ether_address,
                            dht_host="localhost",
                            dht_port=port,
                            db_name="test-{}".format(port),
                            rest_host="localhost",
                            rest_port=port+100,
                            always_be_learning=False,
                            miner_agent=miner_agent,
                            federated_only=federated_only,
                            **ursula_kwargs)

            class MockDatastoreThreadPool(object):
                def callInThread(self, f, *args, **kwargs):
                    return f(*args, **kwargs)

            ursula.datastore_threadpool = MockDatastoreThreadPool()
            ursula.dht_listen()

        if miners is True:
            # TODO: 309
            # stake a random amount
            min_stake, balance = constants.MIN_ALLOWED_LOCKED, ursula.token_balance
            amount = random.randint(min_stake, balance)

            # for a random lock duration
            min_locktime, max_locktime = constants.MIN_LOCKED_PERIODS, constants.MAX_MINTING_PERIODS
            periods = random.randint(min_locktime, max_locktime)

            ursula.initialize_stake(amount=amount, lock_periods=periods)
        else:
            ursula.federated_only = True

        ursulas.add(ursula)
        _TEST_KNOWN_URSULAS_CACHE[ursula.rest_information()[0].port] = ursula

    if know_each_other and not bare:

        for ursula_to_teach in ursulas:
            # Add other Ursulas as known nodes.
            for ursula_to_learn_about in ursulas:
                ursula_to_teach.remember_node(ursula_to_learn_about)

            event_loop.run_until_complete(
                ursula.dht_server.bootstrap(
                    [("localhost", starting_port + _c) for _c in range(len(ursulas))]))
            ursula.publish_dht_information()

    return ursulas


def generate_accounts(w3: Web3, quantity: int) -> List[str]:
    """
    Generate additional unlocked accounts transferring wei_balance to each account on creation.
    """

    addresses = list()
    insecure_passphrase = 'this-is-not-a-secure-password'
    for _ in range(quantity):
        umbral_priv_key = UmbralPrivateKey.gen_key()

        address = w3.personal.importRawKey(private_key=umbral_priv_key.to_bytes(),
                                           passphrase=insecure_passphrase)

        w3.personal.unlockAccount(address, passphrase=insecure_passphrase)
        addresses.append(addresses)
    return addresses


def spawn_random_miners(miner_agent, addresses: list) -> list:
    """
    Deposit and lock a random amount of tokens in the miner escrow
    from each address, "spawning" new Miners.
    """
    from nucypher.blockchain.eth.actors import Miner

    miners = list()
    for address in addresses:
        miner = Miner(miner_agent=miner_agent, checksum_address=address)
        miners.append(miner)

        # stake a random amount
        min_stake, balance = constants.MIN_ALLOWED_LOCKED, miner.token_balance
        amount = random.randint(min_stake, balance)

        # for a random lock duration
        min_locktime, max_locktime = constants.MIN_LOCKED_PERIODS, constants.MAX_MINTING_PERIODS
        periods = random.randint(min_locktime, max_locktime)

        miner.initialize_stake(amount=amount, lock_periods=periods)

    return miners


#
# Test Utility Classes
#

class MockRestMiddleware(RestMiddleware):

    _ursulas = None

    class NotEnoughMockUrsulas(MinerAgent.NotEnoughMiners):
        pass

    def __get_mock_client_by_ursula(self, ursula):
        port = ursula.rest_information()[0].port
        return self.__get_mock_client_by_port(port)

    def __get_mock_client_by_url(self, url):
        port = int(url.split(":")[1])
        return self.__get_mock_client_by_port(port)

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
        mock_client = self.__get_mock_client_by_ursula(arrangement.ursula)
        response = mock_client.post("http://localhost/consider_arrangement", bytes(arrangement))
        assert response.status_code == 200
        return response

    def enact_policy(self, ursula, id, payload):
        mock_client = self.__get_mock_client_by_ursula(ursula)
        response = mock_client.post('http://localhost/kFrag/{}'.format(id.hex()), payload)
        assert response.status_code == 200
        return True, ursula.stamp.as_umbral_pubkey()

    def send_work_order_payload_to_ursula(self, work_order):
        mock_client = self.__get_mock_client_by_ursula(work_order.ursula)
        payload = work_order.payload()
        id_as_hex = work_order.arrangement_id.hex()
        return mock_client.post('http://localhost/kFrag/{}/reencrypt'.format(id_as_hex), payload)

    def get_treasure_map_from_node(self, node, map_id):
        mock_client = self.__get_mock_client_by_ursula(node)
        return mock_client.get("http://localhost/treasure_map/{}".format(map_id))

    def node_information(self, host, port):
        mock_client = self.__get_mock_client_by_port(port)
        response = mock_client.get("http://localhost/public_information")
        return response

    def get_nodes_via_rest(self, url, announce_nodes=None, nodes_i_need=None):
        mock_client = self.__get_mock_client_by_url(url)

        if nodes_i_need:
            # TODO: This needs to actually do something.
            # Include node_ids in the request; if the teacher node doesn't know about the
            # nodes matching these ids, then it will ask other nodes via the DHT or whatever.
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
        mock_client = self.__get_mock_client_by_ursula(node)
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
