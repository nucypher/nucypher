import datetime

import maya
import os
import pytest
import tempfile
from sqlalchemy.engine import create_engine

from constant_sorrow import constants
from nucypher.characters import Alice, Bob
from nucypher.data_sources import DataSource
from nucypher.keystore import keystore
from nucypher.keystore.db import Base
from nucypher.keystore.keypairs import SigningKeypair
from tests.blockchain.eth.utilities import token_airdrop
from tests.utilities import make_ursulas, MockRestMiddleware


@pytest.fixture(scope="module")
def idle_policy(alice, bob):
    """
    Creates a Policy, in a manner typical of how Alice might do it, with a unique uri (soon to be "label" - see #183)
    """
    n = int(constants.NUMBER_OF_URSULAS_IN_NETWORK)
    random_label = b'label://' + os.urandom(32)
    policy = alice.create_policy(bob, label=random_label, m=3, n=n)
    return policy


@pytest.fixture(scope="module")
def enacted_policy(idle_policy, ursulas, mock_miner_agent, mock_token_agent):
    _origin, ursula, *everybody_else = mock_miner_agent.blockchain.interface.w3.eth.accounts
    mock_token_agent.token_airdrop(amount=100000 * constants.M)  # blocks
    mock_miner_agent.spawn_random_miners(addresses=everybody_else)
    mock_miner_agent.blockchain.time_travel(periods=1)

    # Alice has a policy in mind and knows of enough qualifies Ursulas; she crafts an offer for them.
    deposit = constants.NON_PAYMENT(b"0000000")
    contract_end_datetime = maya.now() + datetime.timedelta(days=5)
    network_middleware = MockRestMiddleware()

    idle_policy.make_arrangements(network_middleware, deposit=deposit, quantity=3, expiration=contract_end_datetime)
    idle_policy.enact(network_middleware)  # REST call happens here, as does population of TreasureMap.

    return idle_policy


@pytest.fixture(scope="module")
def alice(mining_ursulas, three_agents):
    token_agent, miner_agent, policy_agent = three_agents
    etherbase, alice, bob, *everyone_else = token_agent.blockchain.interface.w3.eth.accounts

    alice = Alice(network_middleware=MockRestMiddleware(),
                  policy_agent=policy_agent,
                  ether_address=alice,
                  known_nodes=mining_ursulas)
    alice.recruit = lambda *args, **kwargs: [u.ether_address for u in mining_ursulas]

    return alice


@pytest.fixture(scope="module")
def bob(mining_ursulas):
    _bob = Bob(network_middleware=MockRestMiddleware(), known_nodes=mining_ursulas)
    return _bob


# @pytest.fixture(scope="module")
# def ursulas(three_agents):
#     token_agent, miner_agent, policy_agent = three_agents
#     etherbase, alice, bob, *all_yall = token_agent.blockchain.interface.w3.eth.accounts
#     _receipts = token_airdrop(token_agent=token_agent, origin=etherbase, addresses=all_yall, amount=1000000 * constants.M)
#     ursula_addresses = all_yall[:int(constants.NUMBER_OF_URSULAS_IN_NETWORK)]
#
#     _ursulas = make_ursulas(ether_addresses=ursula_addresses,
#                             ursula_starting_port=int(constants.URSULA_PORT_SEED))
#     yield _ursulas
#     # Remove the DBs that have been sprayed hither and yon.
#     for port, ursula in enumerate(_ursulas, start=int(constants.URSULA_PORT_SEED)):
#         os.remove("test-{}".format(port))


@pytest.fixture(scope="module")
def mining_ursulas(three_agents):
    token_agent, miner_agent, policy_agent = three_agents
    etherbase, alice, bob, *all_yall = token_agent.blockchain.interface.w3.eth.accounts
    _receipts = token_airdrop(token_agent=token_agent, origin=etherbase, addresses=all_yall, amount=1000000 * constants.M)
    ursula_addresses = all_yall[:int(constants.NUMBER_OF_URSULAS_IN_NETWORK)]

    _ursulas = make_ursulas(ether_addresses=ursula_addresses,
                            ursula_starting_port=int(constants.URSULA_PORT_SEED),
                            miner_agent=miner_agent,
                            miners=True)
    yield _ursulas
    # Remove the DBs that have been sprayed hither and yon.
    for port, ursula in enumerate(_ursulas, start=int(constants.URSULA_PORT_SEED)):
        os.remove("test-{}".format(port))


@pytest.fixture(scope="module")
def treasure_map_is_set_on_dht(enacted_policy, ursulas):
    network_middleware = MockRestMiddleware()
    enacted_policy.publish_treasure_map(network_middleware, use_dht=True)


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
