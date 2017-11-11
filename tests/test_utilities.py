import asyncio

from nkms.characters import Ursula
from nkms.network.node import NetworkyStuff


def make_fake_ursulas(how_many_ursulas: int, ursula_starting_port: int) -> list:
    """
    :param how_many: How many Ursulas to create.
    :param ursula_starting_port: The port of the first created Ursula; subsequent Ursulas will increment the port number by 1.
    :return: A list of created Ursulas
    """

    event_loop = asyncio.get_event_loop()

    URSULAS = []
    for _u in range(how_many_ursulas):
        _URSULA = Ursula()
        _URSULA.attach_server()
        _URSULA.listen(ursula_starting_port + _u, "127.0.0.1")

        URSULAS.append(_URSULA)

    for _counter, ursula in enumerate(URSULAS):
        event_loop.run_until_complete(
            ursula.server.bootstrap([("127.0.0.1", ursula_starting_port + _c) for _c in range(how_many_ursulas)]))
        ursula.publish_interface_information()

    return URSULAS, range(ursula_starting_port, ursula_starting_port + len(URSULAS))


class MockPolicyOfferResponse(object):
    was_accepted = True


class MockNetworkyStuff(NetworkyStuff):

    def __init__(self, ursulas):
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

    def animate_policy(self, ursula, payload):
        return True, ursula.interface_dht_key()
