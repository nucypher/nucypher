import datetime

import pytest

from nkms.characters import congregate, Alice, Bob
from nkms.network import blockchain_client
from nkms.policy.constants import NON_PAYMENT
from nkms.policy.models import PolicyManagerForAlice
from tests.utilities import NUMBER_OF_URSULAS_IN_NETWORK, MockNetworkyStuff, make_ursulas, \
    URSULA_PORT, EVENT_LOOP


@pytest.fixture(scope="session")
def alices_policy_group(alice, bob):
    """
    Creates a PolicyGroup, in a manner typical of how Alice might do it, with a unique uri.
    """
    alice.__resource_id += b"/unique-again"  # A unique name each time, like a path.
    n = NUMBER_OF_URSULAS_IN_NETWORK

    policy_manager = PolicyManagerForAlice(alice)

    policy_group = policy_manager.create_policy_group(
        bob,
        alice.__resource_id,
        m=3,
        n=n,
    )
    return policy_group


@pytest.fixture(scope="session")
def enacted_policy_group(alices_policy_group, ursulas):
    # Alice has a policy in mind and knows of enough qualifies Ursulas; she crafts an offer for them.
    deposit = NON_PAYMENT
    contract_end_datetime = datetime.datetime.now() + datetime.timedelta(days=5)
    offer = PolicyOffer(alices_policy_group.n, deposit, contract_end_datetime)

    networky_stuff = MockNetworkyStuff(ursulas)
    alices_policy_group.find_n_ursulas(networky_stuff, offer)
    alices_policy_group.enact_policies(networky_stuff)  # REST call happens here, as does population of TreasureMap.

    return alices_policy_group


@pytest.fixture(scope="session")
def alice(ursulas):
    ALICE = Alice()
    ALICE.attach_server()
    ALICE.server.listen(8471)
    ALICE.__resource_id = b"some_resource_id"
    EVENT_LOOP.run_until_complete(ALICE.server.bootstrap([("127.0.0.1", u.port) for u in ursulas]))
    return ALICE


@pytest.fixture(scope="session")
def bob(alice, ursulas):
    BOB = Bob(alice=alice)
    BOB.attach_server()
    BOB.server.listen(8475)
    EVENT_LOOP.run_until_complete(BOB.server.bootstrap([("127.0.0.1", URSULA_PORT)]))
    congregate(alice, BOB, *ursulas)
    return BOB


@pytest.fixture(scope="session")
def ursulas():
    URSULAS = make_ursulas(NUMBER_OF_URSULAS_IN_NETWORK, URSULA_PORT)
    yield URSULAS
    blockchain_client._ursulas_on_blockchain.clear()


@pytest.fixture(scope="session")
def treasure_map_is_set_on_dht(alice, enacted_policy_group):
    _, _, _, _ = enacted_policy_group.publish_treasure_map()