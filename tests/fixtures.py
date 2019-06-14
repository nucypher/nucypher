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

import datetime
import os
import tempfile

import maya
import pytest
from constant_sorrow.constants import NON_PAYMENT
from sqlalchemy.engine import create_engine
from umbral import pre
from umbral.curvebn import CurveBN
from umbral.keys import UmbralPrivateKey
from umbral.signing import Signer
from web3 import Web3

from nucypher.blockchain.economics import TokenEconomics, SlashingEconomics
from nucypher.blockchain.eth.agents import Agency
from nucypher.blockchain.eth.agents import NucypherTokenAgent
from nucypher.blockchain.eth.clients import NuCypherGethDevProcess
from nucypher.blockchain.eth.deployers import (NucypherTokenDeployer,
                                               StakingEscrowDeployer,
                                               PolicyManagerDeployer,
                                               DispatcherDeployer,
                                               AdjudicatorDeployer)
from nucypher.blockchain.eth.interfaces import BlockchainDeployerInterface
from nucypher.blockchain.eth.registry import InMemoryEthereumContractRegistry
from nucypher.blockchain.eth.sol.compile import SolidityCompiler
from nucypher.blockchain.eth.token import NU
from nucypher.characters.lawful import Enrico, Bob
from nucypher.config.characters import UrsulaConfiguration, AliceConfiguration, BobConfiguration
from nucypher.config.constants import BASE_DIR
from nucypher.config.node import CharacterConfiguration
from nucypher.crypto.utils import canonical_address_from_umbral_key
from nucypher.keystore import keystore
from nucypher.keystore.db import Base
from nucypher.policy.models import IndisputableEvidence, WorkOrder
from nucypher.utilities.sandbox.blockchain import token_airdrop, TesterBlockchain
from nucypher.utilities.sandbox.constants import (DEVELOPMENT_ETH_AIRDROP_AMOUNT,
                                                  DEVELOPMENT_TOKEN_AIRDROP_AMOUNT,
                                                  MOCK_POLICY_DEFAULT_M,
                                                  MOCK_URSULA_STARTING_PORT,
                                                  NUMBER_OF_URSULAS_IN_DEVELOPMENT_NETWORK,
                                                  TEMPORARY_DOMAIN,
                                                  TEST_PROVIDER_URI
                                                  )
from nucypher.utilities.sandbox.middleware import MockRestMiddleware
from nucypher.utilities.sandbox.policy import generate_random_label
from nucypher.utilities.sandbox.ursula import (make_decentralized_ursulas,
                                               make_federated_ursulas,
                                               start_pytest_ursula_services)

TEST_CONTRACTS_DIR = os.path.join(BASE_DIR, 'tests', 'blockchain', 'eth', 'contracts', 'contracts')
CharacterConfiguration.DEFAULT_DOMAIN = TEMPORARY_DOMAIN


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
    default_node_config = CharacterConfiguration(dev_mode=True,
                                                 config_root=temp_dir_path,
                                                 download_registry=False)
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
                                        start_learning_now=False,
                                        abort_on_learning_error=True,
                                        federated_only=True,
                                        network_middleware=MockRestMiddleware(),
                                        save_metadata=False,
                                        reload_metadata=False)
    yield ursula_config
    ursula_config.cleanup()


@pytest.fixture(scope="module")
def ursula_decentralized_test_config():
    ursula_config = UrsulaConfiguration(dev_mode=True,
                                        provider_uri=TEST_PROVIDER_URI,
                                        rest_port=MOCK_URSULA_STARTING_PORT,
                                        start_learning_now=False,
                                        abort_on_learning_error=True,
                                        federated_only=False,
                                        network_middleware=MockRestMiddleware(),
                                        download_registry=False,
                                        save_metadata=False,
                                        reload_metadata=False)
    yield ursula_config
    ursula_config.cleanup()


@pytest.fixture(scope="module")
def alice_federated_test_config(federated_ursulas):
    config = AliceConfiguration(dev_mode=True,
                                network_middleware=MockRestMiddleware(),
                                known_nodes=federated_ursulas,
                                federated_only=True,
                                abort_on_learning_error=True,
                                save_metadata=False,
                                reload_metadata=False)
    yield config
    config.cleanup()


@pytest.fixture(scope="module")
def alice_blockchain_test_config(blockchain_ursulas, testerchain):
    config = AliceConfiguration(dev_mode=True,
                                provider_uri=TEST_PROVIDER_URI,
                                checksum_address=testerchain.alice_account,
                                network_middleware=MockRestMiddleware(),
                                known_nodes=blockchain_ursulas[:-1],  # TODO: 1035
                                abort_on_learning_error=True,
                                download_registry=False,
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
def bob_blockchain_test_config(blockchain_ursulas, testerchain):
    config = BobConfiguration(dev_mode=True,
                              provider_uri=TEST_PROVIDER_URI,
                              checksum_address=testerchain.bob_account,
                              network_middleware=MockRestMiddleware(),
                              known_nodes=blockchain_ursulas[:-1],  # TODO: #1035
                              start_learning_now=False,
                              abort_on_learning_error=True,
                              federated_only=False,
                              download_registry=False,
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
                                           expiration=maya.now() + datetime.timedelta(days=5))
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

    # REST call happens here, as does population of TreasureMap.
    responses = idle_federated_policy.enact(network_middleware)

    return idle_federated_policy


@pytest.fixture(scope="module")
def idle_blockchain_policy(blockchain_alice, blockchain_bob, token_economics):
    """
    Creates a Policy, in a manner typical of how Alice might do it, with a unique label
    """
    random_label = generate_random_label()
    expiration = maya.now().add(days=token_economics.minimum_locked_periods//2)
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
def token_economics():
    economics = TokenEconomics()
    return economics


@pytest.fixture(scope='session')
def slashing_economics():
    economics = SlashingEconomics()
    return economics


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
                                                     provider_uri=TEST_PROVIDER_URI)

    # Create the blockchain
    testerchain = TesterBlockchain(interface=deployer_interface,
                                   eth_airdrop=True,
                                   free_transactions=True,
                                   poa=True)

    # Set the deployer address from a freshly created test account
    deployer_interface.deployer_address = testerchain.etherbase_account

    yield testerchain
    deployer_interface.disconnect()
    testerchain.sever_connection()


@pytest.fixture(scope='module')
def agency(testerchain):
    """
    Musketeers, if you will.
    Launch the big three contracts on provided chain,
    make agents for each and return them.
    """

    """Launch all Nucypher ethereum contracts"""
    origin = testerchain.etherbase_account

    token_deployer = NucypherTokenDeployer(blockchain=testerchain, deployer_address=origin)
    token_deployer.deploy()

    staking_escrow_deployer = StakingEscrowDeployer(deployer_address=origin)
    staking_escrow_deployer.deploy(secret_hash=os.urandom(DispatcherDeployer.DISPATCHER_SECRET_LENGTH))

    policy_manager_deployer = PolicyManagerDeployer(deployer_address=origin)
    policy_manager_deployer.deploy(secret_hash=os.urandom(DispatcherDeployer.DISPATCHER_SECRET_LENGTH))

    token_agent = token_deployer.make_agent()  # 1: Token
    staking_agent = staking_escrow_deployer.make_agent()  # 2 Miner Escrow
    policy_agent = policy_manager_deployer.make_agent()  # 3 Policy Agent

    adjudicator_deployer = AdjudicatorDeployer(deployer_address=origin)
    adjudicator_deployer.deploy(secret_hash=os.urandom(DispatcherDeployer.DISPATCHER_SECRET_LENGTH))

    yield token_agent, staking_agent, policy_agent
    Agency.clear()


@pytest.fixture(scope="module", autouse=True)
def clear_out_agency():
    yield
    Agency.clear()


@pytest.fixture(scope="module")
def blockchain_ursulas(agency, ursula_decentralized_test_config):
    token_agent, _staking_agent, _policy_agent = agency
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

    # Stake starts next period (or else signature validation will fail)
    blockchain.time_travel(periods=1)

    # Bootstrap the network
    for ursula_to_teach in _ursulas:
        for ursula_to_learn_about in _ursulas:
            ursula_to_teach.remember_node(ursula_to_learn_about)

    # TODO: #1035 - Move non-staking Ursulas to a new fixture
    # This one is not going to stake
    _non_staking_ursula = make_decentralized_ursulas(ursula_config=ursula_decentralized_test_config,
                                                     ether_addresses=[the_last_ursula],
                                                     stake=False)

    _ursulas.extend(_non_staking_ursula)
    yield _ursulas


@pytest.fixture(scope='module')
def stake_value(token_economics):
    value = NU(token_economics.minimum_allowed_locked * 2, 'NuNit')
    return value


@pytest.fixture(scope='module')
def policy_rate():
    rate = Web3.toWei(21, 'gwei')
    return rate


@pytest.fixture(scope='module')
def policy_value(token_economics, policy_rate):
    value = policy_rate * token_economics.minimum_locked_periods
    return value


@pytest.fixture(scope='module')
def funded_blockchain(testerchain, agency, token_economics):

    # Who are ya'?
    deployer_address, *everyone_else, staking_participant = testerchain.interface.w3.eth.accounts

    # Free ETH!!!
    testerchain.ether_airdrop(amount=DEVELOPMENT_ETH_AIRDROP_AMOUNT)

    # Free Tokens!!!
    token_airdrop(token_agent=NucypherTokenAgent(blockchain=testerchain),
                  origin=deployer_address,
                  addresses=everyone_else,
                  amount=token_economics.minimum_allowed_locked*5)

    # HERE YOU GO
    yield testerchain, deployer_address


@pytest.fixture(scope='module')
def staking_participant(funded_blockchain, blockchain_ursulas):

    # Start up the local fleet
    for teacher in blockchain_ursulas:
        start_pytest_ursula_services(ursula=teacher)

    teachers = list(blockchain_ursulas)
    staking_participant = teachers[-1]  # TODO: # 1035
    return staking_participant


#
# Re-Encryption
#

def _mock_ursula_reencrypts(ursula, corrupt_cfrag: bool = False):
    delegating_privkey = UmbralPrivateKey.gen_key()
    _symmetric_key, capsule = pre._encapsulate(delegating_privkey.get_pubkey())
    signing_privkey = UmbralPrivateKey.gen_key()
    signing_pubkey = signing_privkey.get_pubkey()
    signer = Signer(signing_privkey)
    priv_key_bob = UmbralPrivateKey.gen_key()
    pub_key_bob = priv_key_bob.get_pubkey()
    kfrags = pre.generate_kfrags(delegating_privkey=delegating_privkey,
                                 signer=signer,
                                 receiving_pubkey=pub_key_bob,
                                 threshold=2,
                                 N=4,
                                 sign_delegating_key=False,
                                 sign_receiving_key=False)
    capsule.set_correctness_keys(delegating_privkey.get_pubkey(), pub_key_bob, signing_pubkey)

    ursula_pubkey = ursula.stamp.as_umbral_pubkey()

    alice_address = canonical_address_from_umbral_key(signing_pubkey)
    blockhash = bytes(32)

    specification = bytes(capsule) + bytes(ursula_pubkey) + alice_address + blockhash

    bobs_signer = Signer(priv_key_bob)
    task_signature = bytes(bobs_signer(specification))

    metadata = bytes(ursula.stamp(task_signature))

    cfrag = pre.reencrypt(kfrags[0], capsule, metadata=metadata)

    if corrupt_cfrag:
        cfrag.proof.bn_sig = CurveBN.gen_rand(capsule.params.curve)

    cfrag_signature = bytes(ursula.stamp(bytes(cfrag)))

    bob = Bob.from_public_keys(verifying_key=pub_key_bob)
    task = WorkOrder.Task(capsule, task_signature, cfrag, cfrag_signature)
    work_order = WorkOrder(bob, None, alice_address, [task], None, ursula, blockhash)

    evidence = IndisputableEvidence(task, work_order)
    return evidence


@pytest.fixture(scope='session')
def mock_ursula_reencrypts():
    return _mock_ursula_reencrypts


@pytest.fixture(scope='session')
def geth_dev_node():
    geth = NuCypherGethDevProcess()
    try:
        yield geth
    finally:
        if geth.is_running:
            geth.stop()
            assert not geth.is_running
