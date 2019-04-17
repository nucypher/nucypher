"""
This file is part of nucypher.

nucypher is free software: you can redistribute it and/or modify
it under the terms of the GNU Affero General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

nucypher is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU Affero General Public License for more details.

You should have received a copy of the GNU Affero General Public License
along with nucypher.  If not, see <https://www.gnu.org/licenses/>.
"""

import os
import tempfile

import datetime
import maya
import pytest
from constant_sorrow.constants import NON_PAYMENT
from sqlalchemy.engine import create_engine

from nucypher.blockchain.eth.constants import DISPATCHER_SECRET_LENGTH, MIN_LOCKED_PERIODS
from nucypher.blockchain.eth.deployers import NucypherTokenDeployer, MinerEscrowDeployer, PolicyManagerDeployer
from nucypher.blockchain.eth.interfaces import BlockchainDeployerInterface
from nucypher.blockchain.eth.registry import InMemoryEthereumContractRegistry
from nucypher.blockchain.eth.sol.compile import SolidityCompiler
from nucypher.characters.lawful import Enrico
from nucypher.config.characters import UrsulaConfiguration, AliceConfiguration, BobConfiguration
from nucypher.config.constants import BASE_DIR
from nucypher.config.node import NodeConfiguration
from nucypher.keystore import keystore
from nucypher.keystore.db import Base
from nucypher.utilities.sandbox.blockchain import token_airdrop, TesterBlockchain
from nucypher.utilities.sandbox.constants import (MOCK_URSULA_STARTING_PORT,
                                                  MOCK_POLICY_DEFAULT_M, TESTING_ETH_AIRDROP_AMOUNT)
from nucypher.utilities.sandbox.constants import (NUMBER_OF_URSULAS_IN_DEVELOPMENT_NETWORK,
                                                  DEVELOPMENT_TOKEN_AIRDROP_AMOUNT)
from nucypher.utilities.sandbox.middleware import MockRestMiddleware
from nucypher.utilities.sandbox.policy import generate_random_label
from nucypher.utilities.sandbox.ursula import make_decentralized_ursulas
from nucypher.utilities.sandbox.ursula import make_federated_ursulas

TEST_CONTRACTS_DIR = os.path.join(BASE_DIR, 'tests', 'blockchain', 'eth', 'contracts', 'contracts')


#
# Temporary
#

@pytest.fixture(scope="function")
def tempfile_path():
    fd, path = tempfile.mkstemp()
    yield path
    os.close(fd)
    os.remove(path)


@pytest.fixture(scope="module")
def temp_dir_path():
    temp_dir = tempfile.TemporaryDirectory(prefix='nucypher-test-')
    yield temp_dir.name
    temp_dir.cleanup()


@pytest.fixture(scope="module")
def temp_config_root(temp_dir_path):
    """
    User is responsible for closing the file given at the path.
    """
    default_node_config = NodeConfiguration(dev_mode=True,
                                            config_root=temp_dir_path,
                                            import_seed_registry=False)
    yield default_node_config.config_root
    default_node_config.cleanup()


@pytest.fixture(scope="module")
def test_keystore():
    engine = create_engine('sqlite:///:memory:')
    Base.metadata.create_all(engine)
    test_keystore = keystore.KeyStore(engine)
    yield test_keystore


@pytest.fixture(scope='function')
def certificates_tempdir():
    custom_filepath = '/tmp/nucypher-test-certificates-'
    cert_tmpdir = tempfile.TemporaryDirectory(prefix=custom_filepath)
    yield cert_tmpdir.name
    cert_tmpdir.cleanup()


#
# Configuration
#

@pytest.fixture(scope="module")
def ursula_federated_test_config():
    ursula_config = UrsulaConfiguration(dev_mode=True,
                                        rest_port=MOCK_URSULA_STARTING_PORT,
                                        is_me=True,
                                        start_learning_now=False,
                                        abort_on_learning_error=True,
                                        federated_only=True,
                                        network_middleware=MockRestMiddleware(),
                                        save_metadata=False,
                                        reload_metadata=False)
    yield ursula_config
    ursula_config.cleanup()


@pytest.fixture(scope="module")
@pytest.mark.usefixtures('three_agents')
def ursula_decentralized_test_config(three_agents):
    ursula_config = UrsulaConfiguration(dev_mode=True,
                                        is_me=True,
                                        provider_uri="tester://pyevm",
                                        rest_port=MOCK_URSULA_STARTING_PORT,
                                        start_learning_now=False,
                                        abort_on_learning_error=True,
                                        federated_only=False,
                                        network_middleware=MockRestMiddleware(),
                                        import_seed_registry=False,
                                        save_metadata=False,
                                        reload_metadata=False)
    yield ursula_config
    ursula_config.cleanup()


@pytest.fixture(scope="module")
def alice_federated_test_config(federated_ursulas):
    config = AliceConfiguration(dev_mode=True,
                                is_me=True,
                                network_middleware=MockRestMiddleware(),
                                known_nodes=federated_ursulas,
                                federated_only=True,
                                abort_on_learning_error=True,
                                save_metadata=False,
                                reload_metadata=False)
    yield config
    config.cleanup()


@pytest.fixture(scope="module")
def alice_blockchain_test_config(blockchain_ursulas, three_agents):
    token_agent, miner_agent, policy_agent = three_agents
    config = AliceConfiguration(dev_mode=True,
                                is_me=True,
                                provider_uri="tester://pyevm",
                                checksum_public_address=token_agent.blockchain.alice_account,
                                network_middleware=MockRestMiddleware(),
                                known_nodes=blockchain_ursulas,
                                abort_on_learning_error=True,
                                import_seed_registry=False,
                                save_metadata=False,
                                reload_metadata=False)
    yield config
    config.cleanup()


@pytest.fixture(scope="module")
def bob_federated_test_config():
    config = BobConfiguration(dev_mode=True,
                              network_middleware=MockRestMiddleware(),
                              start_learning_now=False,
                              abort_on_learning_error=True,
                              federated_only=True,
                              save_metadata=False,
                              reload_metadata=False)
    yield config
    config.cleanup()


@pytest.fixture(scope="module")
def bob_blockchain_test_config(blockchain_ursulas, three_agents):
    token_agent, miner_agent, policy_agent = three_agents
    config = BobConfiguration(dev_mode=True,
                              provider_uri="tester://pyevm",
                              checksum_public_address=token_agent.blockchain.bob_account,
                              network_middleware=MockRestMiddleware(),
                              known_nodes=blockchain_ursulas,
                              start_learning_now=False,
                              abort_on_learning_error=True,
                              federated_only=False,
                              import_seed_registry=False,
                              save_metadata=False,
                              reload_metadata=False)
    yield config
    config.cleanup()


#
# Policies
#


@pytest.fixture(scope="module")
def idle_federated_policy(federated_alice, federated_bob):
    """
    Creates a Policy, in a manner typical of how Alice might do it, with a unique label
    """
    m = MOCK_POLICY_DEFAULT_M
    n = NUMBER_OF_URSULAS_IN_DEVELOPMENT_NETWORK
    random_label = generate_random_label()
    policy = federated_alice.create_policy(federated_bob,
                                           label=random_label,
                                           m=m,
                                           n=n,
                                           federated=True)
    return policy


@pytest.fixture(scope="module")
def enacted_federated_policy(idle_federated_policy, federated_ursulas):
    # Alice has a policy in mind and knows of enough qualifies Ursulas; she crafts an offer for them.
    deposit = NON_PAYMENT
    contract_end_datetime = maya.now() + datetime.timedelta(days=5)
    network_middleware = MockRestMiddleware()

    idle_federated_policy.make_arrangements(network_middleware,
                                            value=deposit,
                                            expiration=contract_end_datetime,
                                            handpicked_ursulas=federated_ursulas)

    responses = idle_federated_policy.enact(
        network_middleware)  # REST call happens here, as does population of TreasureMap.

    return idle_federated_policy


@pytest.fixture(scope="module")
def idle_blockchain_policy(blockchain_alice, blockchain_bob):
    """
    Creates a Policy, in a manner typical of how Alice might do it, with a unique label
    """
    random_label = generate_random_label()
    expiration = maya.now().add(days=MIN_LOCKED_PERIODS//2)
    policy = blockchain_alice.create_policy(blockchain_bob,
                                            label=random_label,
                                            m=2, n=3,
                                            value=20*100,
                                            expiration=expiration)
    return policy


@pytest.fixture(scope="module")
def enacted_blockchain_policy(idle_blockchain_policy, blockchain_ursulas):
    # Alice has a policy in mind and knows of enough qualified Ursulas; she crafts an offer for them.
    deposit = NON_PAYMENT(b"0000000")
    contract_end_datetime = maya.now() + datetime.timedelta(days=5)
    network_middleware = MockRestMiddleware()

    idle_blockchain_policy.make_arrangements(network_middleware,
                                             value=deposit,
                                             expiration=contract_end_datetime,
                                             ursulas=list(blockchain_ursulas))

    idle_blockchain_policy.enact(network_middleware)  # REST call happens here, as does population of TreasureMap.
    return idle_blockchain_policy


@pytest.fixture(scope="module")
def capsule_side_channel(enacted_federated_policy):
    enrico = Enrico(policy_encrypting_key=enacted_federated_policy.public_key)
    message_kit, _signature = enrico.encrypt_message(b"Welcome to the flippering.")
    return message_kit, enrico


@pytest.fixture(scope="module")
def random_policy_label():
    yield generate_random_label()


#
# Alice, Bob, and Ursula
#

@pytest.fixture(scope="module")
def federated_alice(alice_federated_test_config):
    _alice = alice_federated_test_config.produce()
    return _alice


@pytest.fixture(scope="module")
def blockchain_alice(alice_blockchain_test_config):
    _alice = alice_blockchain_test_config.produce()
    return _alice


@pytest.fixture(scope="module")
def federated_bob(bob_federated_test_config):
    _bob = bob_federated_test_config.produce()
    return _bob


@pytest.fixture(scope="module")
def blockchain_bob(bob_blockchain_test_config):
    _bob = bob_blockchain_test_config.produce()
    return _bob


@pytest.fixture(scope="module")
def federated_ursulas(ursula_federated_test_config):
    _ursulas = make_federated_ursulas(ursula_config=ursula_federated_test_config,
                                      quantity=NUMBER_OF_URSULAS_IN_DEVELOPMENT_NETWORK)
    yield _ursulas


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
    memory_registry = InMemoryEthereumContractRegistry()

    # Use the the custom provider and registrar to init an interface

    deployer_interface = BlockchainDeployerInterface(compiler=solidity_compiler,  # freshly recompile if not None
                                                     registry=memory_registry,
                                                     provider_uri='tester://pyevm')

    # Create the blockchain
    testerchain = TesterBlockchain(interface=deployer_interface, airdrop=True)

    deployer_interface.deployer_address = testerchain.etherbase_account  # Set the deployer address from a freshly created test account

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
    origin = testerchain.etherbase_account

    token_deployer = NucypherTokenDeployer(blockchain=testerchain, deployer_address=origin)

    token_deployer.deploy()

    token_agent = token_deployer.make_agent()  # 1: Token

    miners_escrow_secret = os.urandom(DISPATCHER_SECRET_LENGTH)
    miner_escrow_deployer = MinerEscrowDeployer(
        deployer_address=origin,
        secret_hash=testerchain.interface.w3.keccak(miners_escrow_secret))

    miner_escrow_deployer.deploy()

    miner_agent = miner_escrow_deployer.make_agent()  # 2 Miner Escrow

    policy_manager_secret = os.urandom(DISPATCHER_SECRET_LENGTH)
    policy_manager_deployer = PolicyManagerDeployer(
        deployer_address=origin,
        secret_hash=testerchain.interface.w3.keccak(policy_manager_secret))

    policy_manager_deployer.deploy()

    policy_agent = policy_manager_deployer.make_agent()  # 3 Policy Agent

    return token_agent, miner_agent, policy_agent


@pytest.fixture(scope="module")
def blockchain_ursulas(three_agents, ursula_decentralized_test_config):
    token_agent, miner_agent, policy_agent = three_agents
    blockchain = token_agent.blockchain

    token_airdrop(origin=blockchain.etherbase_account,
                  addresses=blockchain.ursulas_accounts,
                  token_agent=token_agent,
                  amount=DEVELOPMENT_TOKEN_AIRDROP_AMOUNT)

    # Leave out the last Ursula for manual stake testing
    *all_but_the_last_ursula, the_last_ursula = blockchain.ursulas_accounts

    _ursulas = make_decentralized_ursulas(ursula_config=ursula_decentralized_test_config,
                                          ether_addresses=all_but_the_last_ursula,
                                          stake=True)

    # This one is not going to stake
    _non_staking_ursula = make_decentralized_ursulas(ursula_config=ursula_decentralized_test_config,
                                                     ether_addresses=[the_last_ursula],
                                                     stake=False)

    _ursulas.extend(_non_staking_ursula)
    blockchain.time_travel(periods=1)
    yield _ursulas

