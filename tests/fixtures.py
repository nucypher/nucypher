import datetime
import os
import tempfile

import maya
import pytest
from constant_sorrow import constants
from sqlalchemy.engine import create_engine

from nkms.characters import Alice, Bob
from nkms.crypto.signature import SignatureStamp
from nkms.data_sources import DataSource
from nkms.keystore import keystore
from nkms.keystore.db import Base
from nkms.keystore.keypairs import SigningKeypair
from nkms.network import blockchain_client
from tests.utilities import NUMBER_OF_URSULAS_IN_NETWORK, MockNetworkyStuff, make_ursulas, \
    URSULA_PORT, EVENT_LOOP


@pytest.fixture(scope="module")
def idle_policy(alice, bob):
    """
    Creates a Policy, in a manner typical of how Alice might do it, with a unique uri (soon to be "label" - see #183)
    """
    alice.__resource_id += b"/unique-again"  # A unique name each time, like a path.
    n = NUMBER_OF_URSULAS_IN_NETWORK

    policy = alice.create_policy(
        bob,
        alice.__resource_id,
        m=3,
        n=n,
    )
    return policy


@pytest.fixture(scope="module")
def enacted_policy(idle_policy, ursulas):
    # Alice has a policy in mind and knows of enough qualifies Ursulas; she crafts an offer for them.
    deposit = constants.NON_PAYMENT
    contract_end_datetime = maya.now() + datetime.timedelta(days=5)
    # contract = Contract(idle_policy.n, deposit, contract_end_datetime)

    networky_stuff = MockNetworkyStuff(ursulas)
    found_ursulas = idle_policy.find_ursulas(networky_stuff, deposit, expiration=contract_end_datetime)
    idle_policy.match_kfrags_to_found_ursulas(found_ursulas)
    idle_policy.enact(networky_stuff)  # REST call happens here, as does population of TreasureMap.

    return idle_policy


@pytest.fixture(scope="module")
def alice(ursulas):
    ALICE = Alice()
    ALICE.server.listen(8471)
    ALICE.__resource_id = b"some_resource_id"
    EVENT_LOOP.run_until_complete(ALICE.server.bootstrap([("127.0.0.1", u.dht_port) for u in ursulas]))
    return ALICE


@pytest.fixture(scope="module")
def bob():
    BOB = Bob()
    BOB.server.listen(8475)
    EVENT_LOOP.run_until_complete(BOB.server.bootstrap([("127.0.0.1", URSULA_PORT)]))
    return BOB


@pytest.fixture(scope="module")
def ursulas():
    URSULAS = make_ursulas(NUMBER_OF_URSULAS_IN_NETWORK, URSULA_PORT)
    yield URSULAS
    # Remove the DBs that have been sprayed hither and yon.
    for _u in range(NUMBER_OF_URSULAS_IN_NETWORK):
        port = URSULA_PORT + _u
        os.remove("test-{}".format(port))
    blockchain_client._ursulas_on_blockchain.clear()


@pytest.fixture(scope="module")
def treasure_map_is_set_on_dht(enacted_policy):
    enacted_policy.publish_treasure_map()


@pytest.fixture(scope="module")
def test_keystore():
    engine = create_engine('sqlite:///:memory:')
    Base.metadata.create_all(engine)
    test_keystore = keystore.KeyStore(engine)
    yield test_keystore


@pytest.fixture(scope="module")
def capsule_side_channel(enacted_policy):
    signing_keypair = SigningKeypair()
    data_source = DataSource(policy_pubkey_enc=enacted_policy.public_key(),
                             signer=SignatureStamp(signing_keypair))
    message_kit, _signature = data_source.encapsulate_single_message(b"Welcome to the flippering.")
    return message_kit, data_source


@pytest.fixture(scope="function")
def tempfile_path():
    """
    User is responsible for closing the file given at the path.
    """
    _, path = tempfile.mkstemp()
    yield path
    os.remove(path)
