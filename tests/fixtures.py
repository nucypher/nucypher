import datetime
import os
import tempfile

import maya
import pytest
from constant_sorrow import constants
from sqlalchemy.engine import create_engine

from nucypher.blockchain.eth.chains import Blockchain
from nucypher.characters import Alice, Bob

from nucypher.config.configs import NucypherConfig

from nucypher.data_sources import DataSource
from nucypher.keystore import keystore
from nucypher.keystore.db import Base
from nucypher.keystore.keypairs import SigningKeypair
from nucypher.network import blockchain_client
from tests.utilities import NUMBER_OF_URSULAS_IN_NETWORK, MockNetworkyStuff, make_ursulas, \
    URSULA_PORT, EVENT_LOOP


@pytest.fixture(scope="module")
def nucypher_test_config(blockchain_config):

    config = NucypherConfig(keyring="this is the most secure password in the world.",
                            blockchain_config=blockchain_config)
    yield config
    NucypherConfig.reset()
    Blockchain.sever()
    del config


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
    deposit = constants.NON_PAYMENT(b"0000000")
    contract_end_datetime = maya.now() + datetime.timedelta(days=5)

    networky_stuff = MockNetworkyStuff(ursulas)
    found_ursulas = idle_policy.find_ursulas(networky_stuff, deposit, expiration=contract_end_datetime)
    idle_policy.match_kfrags_to_found_ursulas(found_ursulas)
    idle_policy.enact(networky_stuff)  # REST call happens here, as does population of TreasureMap.

    return idle_policy


@pytest.fixture(scope="module")
def alice(ursulas, mock_policy_agent, nucypher_test_config):
    ALICE = Alice(network_middleware=MockNetworkyStuff(ursulas), policy_agent=mock_policy_agent, config=nucypher_test_config)
    ALICE.server.listen(8471)
    ALICE.__resource_id = b"some_resource_id"
    EVENT_LOOP.run_until_complete(ALICE.server.bootstrap([("127.0.0.1", u.dht_port) for u in ursulas]))
    ALICE.network_bootstrap([("127.0.0.1", u.rest_port) for u in ursulas])
    return ALICE


@pytest.fixture(scope="module")
def bob(ursulas):
    BOB = Bob(network_middleware=MockNetworkyStuff(ursulas))
    return BOB


@pytest.fixture(scope="module")
def ursulas(nucypher_test_config):
    URSULAS = make_ursulas(NUMBER_OF_URSULAS_IN_NETWORK, URSULA_PORT, config=nucypher_test_config)
    yield URSULAS
    # Remove the DBs that have been sprayed hither and yon.
    for _u in range(NUMBER_OF_URSULAS_IN_NETWORK):
        port = URSULA_PORT + _u
        os.remove("test-{}".format(port))
    blockchain_client._ursulas_on_blockchain.clear()


@pytest.fixture(scope="module")
def treasure_map_is_set_on_dht(enacted_policy, ursulas):
    networky_stuff = MockNetworkyStuff(ursulas)
    enacted_policy.publish_treasure_map(networky_stuff, use_dht=True)


@pytest.fixture(scope="module")
def test_keystore():
    engine = create_engine('sqlite:///:memory:')
    Base.metadata.create_all(engine)
    test_keystore = keystore.KeyStore(engine)
    yield test_keystore


@pytest.fixture(scope="module")
def capsule_side_channel(enacted_policy):
    signing_keypair = SigningKeypair()
    data_source = DataSource(policy_pubkey_enc=enacted_policy.public_key,
                             signing_keypair=signing_keypair)
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
