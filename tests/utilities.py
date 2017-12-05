import asyncio

import pytest
from sqlalchemy.engine import create_engine

from apistar.test import TestClient
from nkms.characters import Ursula
from nkms.crypto.fragments import CFrag
from nkms.crypto.utils import RepeatingBytestringSplitter
from nkms.keystore import keystore
from nkms.keystore.db import Base
from nkms.network.node import NetworkyStuff

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
        engine = create_engine('sqlite:///:memory:')
        Base.metadata.create_all(engine)
        ursulas_keystore = keystore.KeyStore(engine)
        _URSULA = Ursula(urulsas_keystore=ursulas_keystore)
        _URSULA.attach_server()
        _URSULA.listen(ursula_starting_port + _u, "127.0.0.1")

        URSULAS.append(_URSULA)

    for _counter, ursula in enumerate(URSULAS):
        event_loop.run_until_complete(
            ursula.server.bootstrap([("127.0.0.1", ursula_starting_port + _c) for _c in range(how_many_ursulas)]))
        ursula.publish_interface_information()

    return URSULAS  # , range(ursula_starting_port, ursula_starting_port + len(URSULAS))


class MockPolicyOfferResponse(object):
    was_accepted = True


class MockNetworkyStuff(NetworkyStuff):
    def __init__(self, ursulas):
        self._ursulas = {u.interface_dht_key(): u for u in ursulas}
        self.ursulas = iter(ursulas)

    def go_live_with_policy(self, ursula, policy_offer):
        return

    def find_ursula(self, id, offer=None):
        if offer:
            try:
                return next(self.ursulas), MockPolicyOfferResponse()
            except StopIteration:
                raise self.NotEnoughQualifiedUrsulas
        else:
            return super().find_ursula(id)

    def enact_policy(self, ursula, hrac, payload):
        mock_client = TestClient(ursula.rest_app)
        response = mock_client.post('http://localhost/kFrag/{}'.format(hrac.hex()), payload)
        return True, ursula.interface_dht_key()

    def get_ursula_by_id(self, ursula_id):
        print(self._ursulas)
        try:
            ursula = self._ursulas[ursula_id]
        except KeyError:
            pytest.fail("No Ursula with ID {}".format(ursula_id))
        return ursula

    def reencrypt(self, work_order):
        print(work_order)
        ursula = self.get_ursula_by_id(work_order.ursula_id)
        mock_client = TestClient(ursula.rest_app)
        payload = work_order.payload()
        response = mock_client.post('http://localhost/kFrag/{}/reencrypt'.format(work_order.kfrag_hrac.hex()), payload)
        cfrags = RepeatingBytestringSplitter(CFrag)(response.content)
        return cfrags
