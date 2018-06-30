import contextlib
import datetime
import os
import tempfile

import maya
import pytest
from sqlalchemy.engine import create_engine

from constant_sorrow import constants
from eth_utils import to_canonical_address, to_checksum_address
from nucypher.characters import Alice, Bob
from nucypher.data_sources import DataSource
from nucypher.keystore import keystore
from nucypher.keystore.db import Base
from nucypher.keystore.keypairs import SigningKeypair
from tests.blockchain.eth.utilities import token_airdrop
from tests.utilities import make_ursulas, MockRestMiddleware


@pytest.fixture(scope="module")
def idle_blockchain_policy(alice, bob):
    """
    Creates a Policy, in a manner typical of how Alice might do it, with a unique uri (soon to be "label" - see #183)
    """
    n = int(constants.NUMBER_OF_URSULAS_IN_NETWORK)
    random_label = b'label://' + os.urandom(32)
    policy = alice.create_policy(bob, label=random_label, m=3, n=n)
    return policy


@pytest.fixture(scope="module")
def idle_federated_policy(alice, bob):
    """
    Creates a Policy, in a manner typical of how Alice might do it, with a unique uri (soon to be "label" - see #183)
    """
    n = int(constants.NUMBER_OF_URSULAS_IN_NETWORK)
    random_label = b'label://' + os.urandom(32)
    policy = alice.create_policy(bob, label=random_label, m=3, n=n, federated=True)
    return policy


@pytest.fixture(scope="module")
def enacted_blockchain_policy(idle_blockchain_policy, ursulas):
    # Alice has a policy in mind and knows of enough qualifies Ursulas; she crafts an offer for them.
    deposit = constants.NON_PAYMENT(b"0000000")
    contract_end_datetime = maya.now() + datetime.timedelta(days=5)
    network_middleware = MockRestMiddleware()

    idle_blockchain_policy.make_arrangements(network_middleware, deposit=deposit, expiration=contract_end_datetime,
                                             ursulas=list(ursulas))
    idle_blockchain_policy.enact(network_middleware)  # REST call happens here, as does population of TreasureMap.

    return idle_blockchain_policy


@pytest.fixture(scope="module")
def enacted_federated_policy(idle_federated_policy, ursulas):
    # Alice has a policy in mind and knows of enough qualifies Ursulas; she crafts an offer for them.
    deposit = constants.NON_PAYMENT(b"0000000")
    contract_end_datetime = maya.now() + datetime.timedelta(days=5)
    network_middleware = MockRestMiddleware()

    idle_federated_policy.make_arrangements(network_middleware,
                                            deposit=deposit,
                                            expiration=contract_end_datetime,
                                            ursulas=ursulas)
    idle_federated_policy.enact(network_middleware)  # REST call happens here, as does population of TreasureMap.

    return idle_federated_policy


@pytest.fixture(scope="module")
def alice(ursulas, three_agents):
    token_agent, miner_agent, policy_agent = three_agents
    etherbase, alice, bob, *everyone_else = token_agent.blockchain.interface.w3.eth.accounts

    alice = Alice(network_middleware=MockRestMiddleware(),
                  policy_agent=policy_agent,
                  ether_address=alice,
                  known_nodes=ursulas,
                  federated_only=True,
                  abort_on_learning_error=True)
    alice.recruit = lambda *args, **kwargs: [u._ether_address for u in ursulas]

    return alice


@pytest.fixture(scope="module")
def bob():
    _bob = Bob(network_middleware=MockRestMiddleware(),
               always_be_learning=False,
               abort_on_learning_error=True,
               federated_only=True)
    return _bob


@pytest.fixture(scope="module")
def ursulas(three_agents):
    token_agent, miner_agent, policy_agent = three_agents
    ether_addresses = [to_checksum_address(os.urandom(20)) for _ in range(constants.NUMBER_OF_URSULAS_IN_NETWORK)]
    _ursulas = make_ursulas(ether_addresses=ether_addresses,
                            ursula_starting_port=int(constants.URSULA_PORT_SEED),
                            miner_agent=miner_agent
                            )
    try:
        yield _ursulas
    finally:
        # Remove the DBs that have been sprayed hither and yon.
        with contextlib.suppress(FileNotFoundError):
            for port, ursula in enumerate(_ursulas, start=int(constants.URSULA_PORT_SEED)):
                os.remove("test-{}".format(port))


@pytest.fixture(scope="module")
def mining_ursulas(three_agents):
    starting_point = constants.URSULA_PORT_SEED + 500
    token_agent, miner_agent, policy_agent = three_agents
    etherbase, alice, bob, *all_yall = token_agent.blockchain.interface.w3.eth.accounts
    _receipts = token_airdrop(token_agent=token_agent, origin=etherbase, addresses=all_yall,
                              amount=1000000 * constants.M)
    ursula_addresses = all_yall[:int(constants.NUMBER_OF_URSULAS_IN_NETWORK)]

    _ursulas = make_ursulas(ether_addresses=ursula_addresses,
                            ursula_starting_port=int(starting_point),
                            miner_agent=miner_agent,
                            miners=True)
    try:
        yield _ursulas
    finally:
        # Remove the DBs that have been sprayed hither and yon.
        with contextlib.suppress(FileNotFoundError):
            for port, ursula in enumerate(_ursulas, start=int(starting_point)):
                os.remove("test-{}".format(port))


@pytest.fixture(scope="module")
def test_keystore():
    engine = create_engine('sqlite:///:memory:')
    Base.metadata.create_all(engine)
    test_keystore = keystore.KeyStore(engine)
    yield test_keystore


@pytest.fixture(scope="module")
def capsule_side_channel(enacted_federated_policy):
    signing_keypair = SigningKeypair()
    data_source = DataSource(policy_pubkey_enc=enacted_federated_policy.public_key,
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
