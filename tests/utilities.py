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
from nkms.policy.models import ContractResponse

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

    return URSULAS


class MockContractResponse(ContractResponse):
    was_accepted = True

    def __bytes__(self):
        return b"This is a contract response; we have no idea what the bytes repr will be."


class MockNetworkyStuff(NetworkyStuff):
    def __init__(self, ursulas):
        self._ursulas = {u.interface_dht_key(): u for u in ursulas}
        self.ursulas = iter(ursulas)

    def go_live_with_policy(self, ursula, policy_offer):
        return

    def find_ursula(self, contract=None):
        if contract:
            try:
                ursula = next(self.ursulas)
            except StopIteration:
                raise self.NotEnoughQualifiedUrsulas
            mock_client = TestClient(ursula.rest_app)
            # contract_response = ursula.consider_contract(contract)
            response = mock_client.post("http://localhost/consider_agreement", bytes(contract))
            return ursula, MockContractResponse()
        else:
            self

    def enact_policy(self, ursula, hrac, payload):
        mock_client = TestClient(ursula.rest_app)
        response = mock_client.post('http://localhost/kFrag/{}'.format(hrac.hex()), payload)
        return True, ursula.interface_dht_key()

    def get_ursula_by_id(self, ursula_id):
        try:
            ursula = self._ursulas[ursula_id]
        except KeyError:
            pytest.fail("No Ursula with ID {}".format(ursula_id))
        return ursula

    def send_work_order_payload_to_ursula(self, work_order, ursula):
        mock_client = TestClient(ursula.rest_app)
        payload = work_order.payload()
        hrac_as_hex = work_order.kfrag_hrac.hex()
        return mock_client.post('http://localhost/kFrag/{}/reencrypt'.format(hrac_as_hex), payload)
