import datetime

import pytest

from nkms.characters import congregate, Alice, Bob
from nkms.crypto.kits import MessageKit
from nkms.crypto.powers import SigningPower, EncryptingPower
from nkms.network import blockchain_client
from nkms.policy.constants import NON_PAYMENT
from tests.utilities import NUMBER_OF_URSULAS_IN_NETWORK, MockNetworkyStuff, make_ursulas, \
    URSULA_PORT, EVENT_LOOP
from sqlalchemy.engine import create_engine
from nkms.keystore import keystore
from nkms.keystore.db import Base
from umbral import pre


@pytest.fixture(scope="module")
def idle_policy(alice, bob):
    """
    Creates a PolicyGroup, in a manner typical of how Alice might do it, with a unique uri.
    """
    alice.__resource_id += b"/unique-again"  # A unique name each time, like a path.
    n = NUMBER_OF_URSULAS_IN_NETWORK

    policy_group = alice.create_policy(
        bob,
        alice.__resource_id,
        m=3,
        n=n,
    )
    return policy_group


@pytest.fixture(scope="module")
def enacted_policy(idle_policy, ursulas):
    # Alice has a policy in mind and knows of enough qualifies Ursulas; she crafts an offer for them.
    deposit = NON_PAYMENT
    contract_end_datetime = datetime.datetime.now() + datetime.timedelta(days=5)
    # contract = Contract(idle_policy.n, deposit, contract_end_datetime)

    networky_stuff = MockNetworkyStuff(ursulas)
    found_ursulas = idle_policy.find_ursulas(networky_stuff, deposit, expiration=contract_end_datetime)
    idle_policy.match_kfrags_to_found_ursulas(found_ursulas)
    idle_policy.enact(networky_stuff)  # REST call happens here, as does population of TreasureMap.

    return idle_policy


@pytest.fixture(scope="module")
def alice(ursulas):
    ALICE = Alice()
    ALICE.attach_server()
    ALICE.server.listen(8471)
    ALICE.__resource_id = b"some_resource_id"
    EVENT_LOOP.run_until_complete(ALICE.server.bootstrap([("127.0.0.1", u.dht_port) for u in ursulas]))
    return ALICE


@pytest.fixture(scope="module")
def bob(alice, ursulas):
    BOB = Bob(alice=alice)
    BOB.attach_server()
    BOB.server.listen(8475)
    EVENT_LOOP.run_until_complete(BOB.server.bootstrap([("127.0.0.1", URSULA_PORT)]))
    congregate(alice, BOB, *ursulas)
    return BOB


@pytest.fixture(scope="module")
def ursulas():
    URSULAS = make_ursulas(NUMBER_OF_URSULAS_IN_NETWORK, URSULA_PORT)
    yield URSULAS
    blockchain_client._ursulas_on_blockchain.clear()


@pytest.fixture(scope="module")
def treasure_map_is_set_on_dht(alice, enacted_policy):
    enacted_policy.publish_treasure_map()


@pytest.fixture(scope="module")
def test_keystore():
    engine = create_engine('sqlite:///:memory:')
    Base.metadata.create_all(engine)
    test_keystore = keystore.KeyStore(engine)
    yield test_keystore


@pytest.fixture(scope="module")
def alicebob_side_channel(alice):
    plaintext = b"Welcome to the flippering."
    ciphertext, capsule = pre.encrypt(alice.public_key(EncryptingPower), plaintext)
    return MessageKit(ciphertext=ciphertext, capsule=capsule,
                      alice_pubkey=alice.public_key(EncryptingPower))


