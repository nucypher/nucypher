"""
This file is part of nucypher.

nucypher is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

nucypher is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with nucypher.  If not, see <https://www.gnu.org/licenses/>.
"""

import os
import tempfile

import datetime
import maya
import pytest
from sqlalchemy.engine import create_engine

from constant_sorrow.constants import NON_PAYMENT
from nucypher.blockchain.eth.constants import DISPATCHER_SECRET_LENGTH
from nucypher.blockchain.eth.deployers import PolicyManagerDeployer, NucypherTokenDeployer, MinerEscrowDeployer
from nucypher.blockchain.eth.interfaces import BlockchainDeployerInterface
from nucypher.blockchain.eth.registry import InMemoryEthereumContractRegistry
from nucypher.blockchain.eth.sol.compile import SolidityCompiler
from nucypher.characters.lawful import Bob
from nucypher.config.characters import UrsulaConfiguration, AliceConfiguration, BobConfiguration
from nucypher.config.constants import BASE_DIR
from nucypher.config.node import NodeConfiguration
from nucypher.data_sources import DataSource
from nucypher.keystore import keystore
from nucypher.keystore.db import Base
from nucypher.keystore.keypairs import SigningKeypair
from nucypher.network.character_control import bob
from nucypher.network.character_control import enrico
from nucypher.utilities.sandbox.blockchain import TesterBlockchain, token_airdrop
from nucypher.utilities.sandbox.constants import (NUMBER_OF_URSULAS_IN_DEVELOPMENT_NETWORK,
                                                  DEVELOPMENT_TOKEN_AIRDROP_AMOUNT, MOCK_URSULA_STARTING_PORT,
                                                  MOCK_POLICY_DEFAULT_M)
from nucypher.utilities.sandbox.middleware import MockRestMiddleware
from nucypher.utilities.sandbox.ursula import make_federated_ursulas, make_decentralized_ursulas

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
    etherbase, alice_address, bob_address, *everyone_else = token_agent.blockchain.interface.w3.eth.accounts

    config = AliceConfiguration(dev_mode=True,
                                is_me=True,
                                provider_uri="tester://pyevm",
                                checksum_public_address=alice_address,
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
    etherbase, alice_address, bob_address, *everyone_else = token_agent.blockchain.interface.w3.eth.accounts

    config = BobConfiguration(dev_mode=True,
                              provider_uri="tester://pyevm",
                              checksum_public_address=bob_address,
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
    random_label = b'label://' + os.urandom(32)
    policy = federated_alice.create_policy(federated_bob, label=random_label, m=m, n=n, federated=True)
    return policy


@pytest.fixture(scope="module")
def enacted_federated_policy(idle_federated_policy, federated_ursulas):
    # Alice has a policy in mind and knows of enough qualifies Ursulas; she crafts an offer for them.
    deposit = NON_PAYMENT
    contract_end_datetime = maya.now() + datetime.timedelta(days=5)
    network_middleware = MockRestMiddleware()

    idle_federated_policy.make_arrangements(network_middleware,
                                            deposit=deposit,
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
    random_label = b'label://' + os.urandom(32)
    policy = blockchain_alice.create_policy(blockchain_bob, label=random_label, m=2, n=3)
    return policy


@pytest.fixture(scope="module")
def enacted_blockchain_policy(idle_blockchain_policy, blockchain_ursulas):
    # Alice has a policy in mind and knows of enough qualifies Ursulas; she crafts an offer for them.
    deposit = NON_PAYMENT(b"0000000")
    contract_end_datetime = maya.now() + datetime.timedelta(days=5)
    network_middleware = MockRestMiddleware()

    idle_blockchain_policy.make_arrangements(network_middleware,
                                             deposit=deposit,
                                             expiration=contract_end_datetime,
                                             ursulas=list(blockchain_ursulas))

    idle_blockchain_policy.enact(network_middleware)  # REST call happens here, as does population of TreasureMap.
    return idle_blockchain_policy


@pytest.fixture(scope="module")
def capsule_side_channel(enacted_federated_policy):
    data_source = DataSource(policy_pubkey_enc=enacted_federated_policy.public_key,
                             signing_keypair=SigningKeypair(),
                             label=enacted_federated_policy.label
                             )
    message_kit, _signature = data_source.encrypt_message(b"Welcome to the flippering.")
    return message_kit, data_source


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


@pytest.fixture(scope="module")
def blockchain_ursulas(three_agents, ursula_decentralized_test_config):
    token_agent, miner_agent, policy_agent = three_agents
    etherbase, alice, bob, *all_yall = token_agent.blockchain.interface.w3.eth.accounts

    ursula_addresses = all_yall[:NUMBER_OF_URSULAS_IN_DEVELOPMENT_NETWORK]

    token_airdrop(origin=etherbase,
                  addresses=ursula_addresses,
                  token_agent=token_agent,
                  amount=DEVELOPMENT_TOKEN_AIRDROP_AMOUNT)

    _ursulas = make_decentralized_ursulas(ursula_config=ursula_decentralized_test_config,
                                          ether_addresses=ursula_addresses,
                                          stake=True)

    token_agent.blockchain.time_travel(periods=1)
    yield _ursulas


@pytest.fixture(scope='module')
def alice_control(federated_alice, federated_ursulas):
    teacher_node = list(federated_ursulas)[0]
    alice_control = federated_alice.make_wsgi_app(teacher_node)
    alice_control.config['DEBUG'] = True
    alice_control.config['TESTING'] = True
    yield alice_control.test_client()


@pytest.fixture(scope='module')
def bob_control(federated_bob, federated_ursulas):
    teacher_node = list(federated_ursulas)[0]
    bob_control = bob.make_bob_control(federated_bob, teacher_node)
    bob_control.config['DEBUG'] = True
    bob_control.config['TESTING'] = True
    yield bob_control.test_client()


@pytest.fixture(scope='module')
def enrico_control(capsule_side_channel):
    _, data_source = capsule_side_channel
    enrico_control = enrico.make_enrico_control(data_source)
    enrico_control.config['DEBUG'] = True
    enrico_control.config['TESTING'] = True
    yield enrico_control.test_client()


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
    testerchain = TesterBlockchain(interface=deployer_interface,
                                   test_accounts=NUMBER_OF_URSULAS_IN_DEVELOPMENT_NETWORK,
                                   airdrop=False)

    origin, *everyone = testerchain.interface.w3.eth.accounts
    deployer_interface.deployer_address = origin  # Set the deployer address from a freshly created test account
    testerchain.ether_airdrop(amount=1000000000)  # TODO: Use test constant

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

    token_deployer.deploy()

    token_agent = token_deployer.make_agent()              # 1: Token

    miners_escrow_secret = os.urandom(DISPATCHER_SECRET_LENGTH)
    miner_escrow_deployer = MinerEscrowDeployer(
        deployer_address=origin,
        secret_hash=testerchain.interface.w3.keccak(miners_escrow_secret))

    miner_escrow_deployer.deploy()

    miner_agent = miner_escrow_deployer.make_agent()       # 2 Miner Escrow

    policy_manager_secret = os.urandom(DISPATCHER_SECRET_LENGTH)
    policy_manager_deployer = PolicyManagerDeployer(
        deployer_address=origin,
        secret_hash=testerchain.interface.w3.keccak(policy_manager_secret))

    policy_manager_deployer.deploy()

    policy_agent = policy_manager_deployer.make_agent()    # 3 Policy Agent

    return token_agent, miner_agent, policy_agent
