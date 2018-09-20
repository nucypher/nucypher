import contextlib
import datetime
import os
import tempfile

import maya
import pytest
from constant_sorrow import constants
from sqlalchemy.engine import create_engine

from nucypher.blockchain.eth.deployers import PolicyManagerDeployer, NucypherTokenDeployer, MinerEscrowDeployer
from nucypher.blockchain.eth.interfaces import BlockchainDeployerInterface
from nucypher.blockchain.eth.registry import TemporaryEthereumContractRegistry
from nucypher.blockchain.eth.sol.compile import SolidityCompiler
from nucypher.characters.lawful import Bob
from nucypher.config.characters import UrsulaConfiguration, AliceConfiguration
from nucypher.config.constants import TEST_CONTRACTS_DIR
from nucypher.config.node import NodeConfiguration
from nucypher.data_sources import DataSource
from nucypher.keystore import keystore
from nucypher.keystore.db import Base
from nucypher.keystore.keypairs import SigningKeypair
from nucypher.utilities.sandbox.blockchain import TesterBlockchain, token_airdrop
from nucypher.utilities.sandbox.constants import (DEFAULT_NUMBER_OF_URSULAS_IN_DEVELOPMENT_NETWORK,
                                                  DEVELOPMENT_TOKEN_AIRDROP_AMOUNT)
from nucypher.utilities.sandbox.middleware import MockRestMiddleware
from nucypher.utilities.sandbox.ursula import make_federated_ursulas, make_decentralized_ursulas


#
# Temporary
#

@pytest.fixture(scope="function")
def tempfile_path():
    fd, path = tempfile.mkstemp()
    yield path
    os.close(fd)
    os.remove(path)


@pytest.fixture(scope="session")
def temp_dir_path():
    temp_dir = tempfile.TemporaryDirectory(prefix='nucypher-test-')
    yield temp_dir.name
    temp_dir.cleanup()


@pytest.fixture(scope="session")
def temp_config_root(temp_dir_path):
    """
    User is responsible for closing the file given at the path.
    """
    default_node_config = NodeConfiguration(temp=True,
                                            auto_initialize=True,
                                            config_root=temp_dir_path)
    yield default_node_config.config_root


@pytest.fixture(scope="module")
def test_keystore():
    engine = create_engine('sqlite:///:memory:')
    Base.metadata.create_all(engine)
    test_keystore = keystore.KeyStore(engine)
    yield test_keystore


#
# Configuration
#

@pytest.fixture(scope="module")
def ursula_federated_test_config():

    ursula_config = UrsulaConfiguration(temp=True,
                                        auto_initialize=True,
                                        is_me=True,
                                        always_be_learning=False,
                                        abort_on_learning_error=True,
                                        federated_only=True)
    yield ursula_config


@pytest.fixture(scope="module")
def ursula_decentralized_test_config(three_agents):
    token_agent, miner_agent, policy_agent = three_agents

    ursula_config = UrsulaConfiguration(temp=True,
                                        auto_initialize=True,
                                        is_me=True,
                                        always_be_learning=False,
                                        abort_on_learning_error=True,
                                        miner_agent=miner_agent,
                                        federated_only=False)
    yield ursula_config


@pytest.fixture(scope="module")
def alice_federated_test_config(federated_ursulas):
    config = AliceConfiguration(temp=True,
                                auto_initialize=True,
                                is_me=True,
                                network_middleware=MockRestMiddleware(),
                                known_nodes=federated_ursulas,
                                federated_only=True,
                                abort_on_learning_error=True)
    yield config


@pytest.fixture(scope="module")
def alice_blockchain_test_config(blockchain_ursulas, three_agents):
    token_agent, miner_agent, policy_agent = three_agents
    etherbase, alice_address, bob_address, *everyone_else = token_agent.blockchain.interface.w3.eth.accounts

    config = AliceConfiguration(temp=True,
                                is_me=True,
                                auto_initialize=True,
                                network_middleware=MockRestMiddleware(),
                                policy_agent=policy_agent,
                                known_nodes=blockchain_ursulas,
                                abort_on_learning_error=True,
                                checksum_address=alice_address)
    yield config


#
# Policies
#


@pytest.fixture(scope="module")
def idle_federated_policy(alice, bob):
    """
    Creates a Policy, in a manner typical of how Alice might do it, with a unique uri (soon to be "label" - see #183)
    """
    n = DEFAULT_NUMBER_OF_URSULAS_IN_DEVELOPMENT_NETWORK
    random_label = b'label://' + os.urandom(32)
    policy = alice.create_policy(bob, label=random_label, m=3, n=n, federated=True)
    return policy


@pytest.fixture(scope="module")
def enacted_federated_policy(idle_federated_policy, federated_ursulas):
    # Alice has a policy in mind and knows of enough qualifies Ursulas; she crafts an offer for them.
    deposit = constants.NON_PAYMENT
    contract_end_datetime = maya.now() + datetime.timedelta(days=5)
    network_middleware = MockRestMiddleware()

    idle_federated_policy.make_arrangements(network_middleware,
                                            deposit=deposit,
                                            expiration=contract_end_datetime,
                                            handpicked_ursulas=federated_ursulas)

    responses = idle_federated_policy.enact(network_middleware)  # REST call happens here, as does population of TreasureMap.

    return idle_federated_policy


@pytest.fixture(scope="module")
def idle_blockchain_policy(blockchain_alice, bob):
    """
    Creates a Policy, in a manner typical of how Alice might do it, with a unique uri (soon to be "label" - see #183)
    """
    random_label = b'label://' + os.urandom(32)
    policy = blockchain_alice.create_policy(bob, label=random_label, m=2, n=3)
    return policy


@pytest.fixture(scope="module")
def enacted_blockchain_policy(idle_blockchain_policy, blockchain_ursulas):
    # Alice has a policy in mind and knows of enough qualifies Ursulas; she crafts an offer for them.
    deposit = constants.NON_PAYMENT(b"0000000")
    contract_end_datetime = maya.now() + datetime.timedelta(days=5)
    network_middleware = MockRestMiddleware()

    idle_blockchain_policy.make_arrangements(network_middleware, deposit=deposit, expiration=contract_end_datetime,
                                             ursulas=list(blockchain_ursulas))
    idle_blockchain_policy.enact(network_middleware)  # REST call happens here, as does population of TreasureMap.

    return idle_blockchain_policy


#
# Alice, Bob, and Capsule
#

@pytest.fixture(scope="module")
def alice(alice_federated_test_config):
    alice = alice_federated_test_config.produce()
    return alice


@pytest.fixture(scope="module")
def blockchain_alice(alice_blockchain_test_config):
    alice = alice_blockchain_test_config.produce()
    return alice


@pytest.fixture(scope="module")
def bob():
    _bob = Bob(network_middleware=MockRestMiddleware(),
               always_be_learning=False,
               abort_on_learning_error=True,
               federated_only=True)
    return _bob


@pytest.fixture(scope="module")
def capsule_side_channel(enacted_federated_policy):
    signing_keypair = SigningKeypair()
    data_source = DataSource(policy_pubkey_enc=enacted_federated_policy.public_key,
                             signing_keypair=signing_keypair)
    message_kit, _signature = data_source.encapsulate_single_message(b"Welcome to the flippering.")
    return message_kit, data_source


#
# Ursulas
#

@pytest.fixture(scope="module")
def federated_ursulas(ursula_federated_test_config):
    _ursulas = None
    try:
        _ursulas = make_federated_ursulas(ursula_config=ursula_federated_test_config,
                                          quantity=DEFAULT_NUMBER_OF_URSULAS_IN_DEVELOPMENT_NETWORK)
        yield _ursulas
    finally:
        if _ursulas:
            # Remove the DBs that have been sprayed hither and yon.
            with contextlib.suppress(FileNotFoundError):
                for ursula in _ursulas:
                    os.remove(ursula.datastore.engine.engine.url.database)


@pytest.fixture(scope="module")
def blockchain_ursulas(three_agents, ursula_decentralized_test_config):

    token_agent, miner_agent, policy_agent = three_agents
    etherbase, alice, bob, *all_yall = token_agent.blockchain.interface.w3.eth.accounts

    ursula_addresses = all_yall[:DEFAULT_NUMBER_OF_URSULAS_IN_DEVELOPMENT_NETWORK]

    token_airdrop(origin=etherbase,
                  addresses=ursula_addresses,
                  token_agent=token_agent,
                  amount=DEVELOPMENT_TOKEN_AIRDROP_AMOUNT)

    _ursulas = None
    try:
        _ursulas = make_decentralized_ursulas(ursula_config=ursula_decentralized_test_config,
                                              ether_addresses=ursula_addresses,
                                              stake=True)
        yield _ursulas
    finally:
        if _ursulas:
            # Remove the DBs that have been sprayed hither and yon.
            with contextlib.suppress(FileNotFoundError):
                for ursula in _ursulas:
                    os.remove(ursula.datastore.engine.engine.url.database)


#
# Blockchain
#

@pytest.fixture(scope='session')
def solidity_compiler():
    """Doing this more than once per session will result in slower test run times."""
    compiler = SolidityCompiler(test_contract_dir=TEST_CONTRACTS_DIR)
    yield compiler


@pytest.fixture(scope='module')
def testerchain(solidity_compiler):
    """
    https: // github.com / ethereum / eth - tester     # available-backends
    """

    temp_registrar = TemporaryEthereumContractRegistry()

    # Use the the custom provider and registrar to init an interface

    deployer_interface = BlockchainDeployerInterface(compiler=solidity_compiler,  # freshly recompile if not None
                                                     registry=temp_registrar,
                                                     provider_uri='pyevm://tester')

    # Create the blockchain
    testerchain = TesterBlockchain(interface=deployer_interface,
                                   test_accounts=DEFAULT_NUMBER_OF_URSULAS_IN_DEVELOPMENT_NETWORK,
                                   airdrop=False)

    origin, *everyone = testerchain.interface.w3.eth.accounts
    deployer_interface.deployer_address = origin  # Set the deployer address from a freshly created test account

    yield testerchain
    testerchain.sever_connection()


@pytest.fixture(scope='module')
def three_agents(testerchain):
    """
    Musketeers, if you will.
    Launch the big three contracts on provided chain,
    make agents for each and return them.
    """

    """Launch all Nucypher ethereum contracts"""
    origin, *everybody_else = testerchain.interface.w3.eth.accounts

    token_deployer = NucypherTokenDeployer(blockchain=testerchain, deployer_address=origin)
    token_deployer.arm()
    token_deployer.deploy()

    token_agent = token_deployer.make_agent()

    miners_escrow_secret = os.urandom(constants.DISPATCHER_SECRET_LENGTH)
    miner_escrow_deployer = MinerEscrowDeployer(
        token_agent=token_agent,
        deployer_address=origin,
        secret_hash=testerchain.interface.w3.sha3(miners_escrow_secret))
    miner_escrow_deployer.arm()
    miner_escrow_deployer.deploy()

    miner_agent = miner_escrow_deployer.make_agent()

    policy_manager_secret = os.urandom(constants.DISPATCHER_SECRET_LENGTH)
    policy_manager_deployer = PolicyManagerDeployer(
        miner_agent=miner_agent,
        deployer_address=origin,
        secret_hash=testerchain.interface.w3.sha3(policy_manager_secret))
    policy_manager_deployer.arm()
    policy_manager_deployer.deploy()

    policy_agent = policy_manager_deployer.make_agent()

    return token_agent, miner_agent, policy_agent
