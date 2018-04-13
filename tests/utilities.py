import asyncio

from apistar.test import TestClient

from nkms.characters import Ursula
from nkms.network.node import NetworkyStuff
from nkms.policy.models import ArrangementResponse

NUMBER_OF_URSULAS_IN_NETWORK = 6

EVENT_LOOP = asyncio.get_event_loop()
asyncio.set_event_loop(EVENT_LOOP)

URSULA_PORT = 7468
NUMBER_OF_URSULAS_IN_NETWORK = 6


def make_ursulas(how_many_ursulas: int, ursula_starting_port: int) -> list:
    """
    :param how_many_ursulas: How many Ursulas to create.
    :param ursula_starting_port: The port of the first created Ursula; subsequent Ursulas will increment the port number by 1.
    :return: A list of created Ursulas
    """
    event_loop = asyncio.get_event_loop()

    URSULAS = []
    for _u in range(how_many_ursulas):
        port = ursula_starting_port + _u
        _URSULA = Ursula(dht_port=port, dht_interface="127.0.0.1", db_name="test-{}".format(port))

        class MockDatastoreThreadPool(object):
            def callInThread(self, f, *args, **kwargs):
                return f(*args, **kwargs)

        _URSULA.datastore_threadpool = MockDatastoreThreadPool()
        _URSULA.listen()

        URSULAS.append(_URSULA)

    for _counter, ursula in enumerate(URSULAS):
        event_loop.run_until_complete(
            ursula.server.bootstrap([("127.0.0.1", ursula_starting_port + _c) for _c in range(how_many_ursulas)]))
        ursula.publish_dht_information()

    return URSULAS


class MockArrangementResponse(ArrangementResponse):
    was_accepted = True

    def __bytes__(self):
        return b"This is a arrangement response; we have no idea what the bytes repr will be."


class MockNetworkyStuff(NetworkyStuff):
    def __init__(self, ursulas):
        self._ursulas = {u.interface_dht_key(): u for u in ursulas}
        self.ursulas = iter(ursulas)

    def go_live_with_policy(self, ursula, policy_offer):
        return

    def find_ursula(self, arrangement=None):
        try:
            ursula = next(self.ursulas)
        except StopIteration:
            raise self.NotEnoughQualifiedUrsulas
        mock_client = TestClient(ursula.rest_app)
        response = mock_client.post("http://localhost/consider_arrangement", bytes(arrangement))
        return ursula, MockArrangementResponse()

    def enact_policy(self, ursula, hrac, payload):
        mock_client = TestClient(ursula.rest_app)
        response = mock_client.post('http://localhost/kFrag/{}'.format(hrac.hex()), payload)
        return True, ursula.interface_dht_key()

    def send_work_order_payload_to_ursula(self, work_order):
        mock_client = TestClient(work_order.ursula.rest_app)
        payload = work_order.payload()
        hrac_as_hex = work_order.kfrag_hrac.hex()
        return mock_client.post('http://localhost/kFrag/{}/reencrypt'.format(hrac_as_hex), payload)

    def get_treasure_map_from_node(self, node, map_id):
        mock_client = TestClient(node.rest_app)
        return mock_client.get("http://localhost/treasure_map/{}".format(map_id.hex()))

