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
import random
import tempfile

import maya
import pytest
from constant_sorrow.constants import NON_PAYMENT
from sqlalchemy.engine import create_engine
from twisted.logger import Logger
from umbral import pre
from umbral.curvebn import CurveBN
from umbral.keys import UmbralPrivateKey
from umbral.signing import Signer
from web3 import Web3

from nucypher.blockchain.economics import TokenEconomics, SlashingEconomics
from nucypher.blockchain.eth.actors import Staker, StakeHolder
from nucypher.blockchain.eth.agents import NucypherTokenAgent
from nucypher.blockchain.eth.clients import NuCypherGethDevProcess
from nucypher.blockchain.eth.deployers import (NucypherTokenDeployer,
                                               StakingEscrowDeployer,
                                               PolicyManagerDeployer,
                                               DispatcherDeployer,
                                               AdjudicatorDeployer)
from nucypher.blockchain.eth.interfaces import BlockchainInterfaceFactory
from nucypher.blockchain.eth.registry import InMemoryContractRegistry
from nucypher.blockchain.eth.sol.compile import SolidityCompiler
from nucypher.blockchain.eth.token import NU
from nucypher.characters.lawful import Enrico, Bob
from nucypher.config.characters import UrsulaConfiguration, AliceConfiguration, BobConfiguration
from nucypher.config.node import CharacterConfiguration
from nucypher.crypto.powers import TransactingPower
from nucypher.crypto.utils import canonical_address_from_umbral_key
from nucypher.keystore import keystore
from nucypher.keystore.db import Base
from nucypher.policy.collections import IndisputableEvidence, WorkOrder
from nucypher.utilities.sandbox.blockchain import token_airdrop, TesterBlockchain
from nucypher.utilities.sandbox.constants import (DEVELOPMENT_ETH_AIRDROP_AMOUNT,
                                                  DEVELOPMENT_TOKEN_AIRDROP_AMOUNT,
                                                  MOCK_POLICY_DEFAULT_M,
                                                  MOCK_URSULA_STARTING_PORT,
                                                  NUMBER_OF_URSULAS_IN_DEVELOPMENT_NETWORK,
                                                  TEMPORARY_DOMAIN,
                                                  TEST_PROVIDER_URI,
                                                  INSECURE_DEVELOPMENT_PASSWORD)
from nucypher.utilities.sandbox.middleware import MockRestMiddleware
from nucypher.utilities.sandbox.policy import generate_random_label
from nucypher.utilities.sandbox.ursula import (make_decentralized_ursulas,
                                               make_federated_ursulas)

CharacterConfiguration.DEFAULT_DOMAIN = TEMPORARY_DOMAIN

test_logger = Logger("test-logger")

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
                                        reload_metadata=False,)
    yield ursula_config
    ursula_config.cleanup()


@pytest.fixture(scope="module")
def ursula_decentralized_test_config(test_registry):
    ursula_config = UrsulaConfiguration(dev_mode=True,
                                        provider_uri=TEST_PROVIDER_URI,
                                        rest_port=MOCK_URSULA_STARTING_PORT,
                                        start_learning_now=False,
                                        abort_on_learning_error=True,
                                        federated_only=False,
                                        network_middleware=MockRestMiddleware(),
                                        save_metadata=False,
                                        reload_metadata=False,
                                        registry=test_registry)
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
def alice_blockchain_test_config(blockchain_ursulas, testerchain, test_registry):
    config = AliceConfiguration(dev_mode=True,
                                provider_uri=TEST_PROVIDER_URI,
                                checksum_address=testerchain.alice_account,
                                network_middleware=MockRestMiddleware(),
                                known_nodes=blockchain_ursulas,
                                abort_on_learning_error=True,
                                save_metadata=False,
                                reload_metadata=False,
                                registry=test_registry)
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
def bob_blockchain_test_config(blockchain_ursulas, testerchain, test_registry):
    config = BobConfiguration(dev_mode=True,
                              provider_uri=TEST_PROVIDER_URI,
                              checksum_address=testerchain.bob_account,
                              network_middleware=MockRestMiddleware(),
                              known_nodes=blockchain_ursulas,
                              start_learning_now=False,
                              abort_on_learning_error=True,
                              federated_only=False,
                              save_metadata=False,
                              reload_metadata=False,
                              registry=test_registry)
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
    network_middleware = MockRestMiddleware()

    idle_federated_policy.make_arrangements(network_middleware, handpicked_ursulas=federated_ursulas)

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
    class _CapsuleSideChannel:
        def __init__(self):
            self.reset()

        def __call__(self):
            enrico = Enrico(policy_encrypting_key=enacted_federated_policy.public_key)
            message = "Welcome to flippering number {}.".format(len(self.messages)).encode()
            message_kit, _signature = enrico.encrypt_message(message)
            self.messages.append((message_kit, enrico))
            return message_kit, enrico

        def reset(self):
            self.messages = []
            self()

    return _CapsuleSideChannel()


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
def blockchain_alice(alice_blockchain_test_config, testerchain):
    _alice = alice_blockchain_test_config.produce()
    return _alice


@pytest.fixture(scope="module")
def federated_bob(bob_federated_test_config):
    _bob = bob_federated_test_config.produce()
    return _bob


@pytest.fixture(scope="module")
def blockchain_bob(bob_blockchain_test_config, testerchain):
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
    compiler = SolidityCompiler()
    yield compiler


@pytest.fixture(scope='module')
def test_registry():
    registry = InMemoryContractRegistry()
    return registry


def _make_testerchain():
    """
    https://github.com/ethereum/eth-tester     # available-backends
    """
    # Create the blockchain
    testerchain = TesterBlockchain(eth_airdrop=True, free_transactions=True)
    BlockchainInterfaceFactory.register_interface(interface=testerchain)

    # Mock TransactingPower Consumption (Deployer)
    testerchain.transacting_power = TransactingPower(password=INSECURE_DEVELOPMENT_PASSWORD,
                                                     account=testerchain.etherbase_account)
    testerchain.transacting_power.activate()
    return testerchain


@pytest.fixture(scope='session')
def _testerchain():
    testerchain = _make_testerchain()
    yield testerchain


@pytest.fixture(scope='module')
def testerchain(_testerchain):
    testerchain = _testerchain

    coinbase, *addresses = testerchain.client.accounts

    for address in addresses:
        balance = testerchain.client.get_balance(address)
        spent = DEVELOPMENT_ETH_AIRDROP_AMOUNT - balance

        if spent > 0:
            tx = {'to': address, 'from': coinbase, 'value': spent}
            txhash = testerchain.w3.eth.sendTransaction(tx)

            _receipt = testerchain.wait_for_receipt(txhash)
            eth_amount = Web3().fromWei(spent, 'ether')
            testerchain.log.info("Airdropped {} ETH {} -> {}".format(eth_amount, tx['from'], tx['to']))
    yield testerchain


def _make_agency(testerchain, test_registry):
    """
    Launch the big three contracts on provided chain,
    make agents for each and return them.
    """
    origin = testerchain.etherbase_account

    token_deployer = NucypherTokenDeployer(deployer_address=origin, registry=test_registry)
    token_deployer.deploy()

    staking_escrow_deployer = StakingEscrowDeployer(deployer_address=origin, registry=test_registry)
    staking_escrow_deployer.deploy(secret_hash=os.urandom(DispatcherDeployer.DISPATCHER_SECRET_LENGTH))

    policy_manager_deployer = PolicyManagerDeployer(deployer_address=origin, registry=test_registry)
    policy_manager_deployer.deploy(secret_hash=os.urandom(DispatcherDeployer.DISPATCHER_SECRET_LENGTH))

    adjudicator_deployer = AdjudicatorDeployer(deployer_address=origin, registry=test_registry)
    adjudicator_deployer.deploy(secret_hash=os.urandom(DispatcherDeployer.DISPATCHER_SECRET_LENGTH))

    token_agent = token_deployer.make_agent()              # 1 Token
    staking_agent = staking_escrow_deployer.make_agent()   # 2 Miner Escrow
    policy_agent = policy_manager_deployer.make_agent()    # 3 Policy Agent
    _adjudicator_agent = adjudicator_deployer.make_agent()  # 4 Adjudicator

    # TODO: Perhaps we should get rid of returning these agents here.
    # What's important is deploying and creating the first agent for each contract,
    # and since agents are singletons, in tests it's only necessary to call the agent
    # constructor again to receive the existing agent.
    #
    # For example:
    #     staking_agent = StakingEscrowAgent()
    #
    # This is more clear than how we currently obtain an agent instance in tests:
    #     _, staking_agent, _ = agency
    #
    # Other advantages is that it's closer to how agents should be use (i.e., there
    # are no fixtures IRL) and it's more extensible (e.g., AdjudicatorAgent)

    return token_agent, staking_agent, policy_agent


@pytest.fixture(scope='module')
def agency(testerchain, test_registry):
    agents = _make_agency(testerchain=testerchain, test_registry=test_registry)
    yield agents


@pytest.fixture(scope='module')
def session_agency(_testerchain, test_registry):
    testerchain = _testerchain
    agents = _make_agency(testerchain=testerchain, test_registry=test_registry)
    yield agents


@pytest.fixture(scope="module")
def stakers(testerchain, agency, token_economics, test_registry):
    token_agent, _staking_agent, _policy_agent = agency
    blockchain = token_agent.blockchain

    # Mock Powerup consumption (Deployer)
    blockchain.transacting_power = TransactingPower(password=INSECURE_DEVELOPMENT_PASSWORD,
                                                    account=blockchain.etherbase_account)
    blockchain.transacting_power.activate()

    token_airdrop(origin=blockchain.etherbase_account,
                  addresses=blockchain.stakers_accounts,
                  token_agent=token_agent,
                  amount=DEVELOPMENT_TOKEN_AIRDROP_AMOUNT)

    stakers = list()
    for index, account in enumerate(blockchain.stakers_accounts):
        staker = Staker(is_me=True, checksum_address=account, registry=test_registry)

        # Mock TransactingPower consumption
        staker.transacting_power = TransactingPower(password=INSECURE_DEVELOPMENT_PASSWORD, account=account)
        staker.transacting_power.activate()

        min_stake, balance = token_economics.minimum_allowed_locked, staker.token_balance
        amount = random.randint(min_stake, balance)

        # for a random lock lock_periods
        min_locktime, max_locktime = token_economics.minimum_locked_periods, token_economics.maximum_locked_periods
        periods = random.randint(min_locktime, max_locktime)

        staker.initialize_stake(amount=amount, lock_periods=periods)

        # We assume that the staker knows in advance the account of her worker
        worker_address = blockchain.ursula_account(index)
        staker.set_worker(worker_address=worker_address)

        stakers.append(staker)

    # Stake starts next period (or else signature validation will fail)
    blockchain.time_travel(periods=1)

    yield stakers


@pytest.fixture(scope="module")
def blockchain_ursulas(testerchain, stakers, ursula_decentralized_test_config):

    _ursulas = make_decentralized_ursulas(ursula_config=ursula_decentralized_test_config,
                                          stakers_addresses=testerchain.stakers_accounts,
                                          workers_addresses=testerchain.ursulas_accounts,
                                          confirm_activity=True)

    testerchain.time_travel(periods=1)

    # Bootstrap the network
    for ursula_to_teach in _ursulas:
        for ursula_to_learn_about in _ursulas:
            ursula_to_teach.remember_node(ursula_to_learn_about)

    yield _ursulas


@pytest.fixture(scope="module")
def idle_staker(testerchain, agency):
    token_agent, _staking_agent, _policy_agent = agency

    idle_staker_account = testerchain.unassigned_accounts[-2]

    # Mock Powerup consumption (Deployer)
    testerchain.transacting_power = TransactingPower(account=testerchain.etherbase_account)

    token_airdrop(origin=testerchain.etherbase_account,
                  addresses=[idle_staker_account],
                  token_agent=token_agent,
                  amount=DEVELOPMENT_TOKEN_AIRDROP_AMOUNT)

    # Prepare idle staker
    idle_staker = Staker(is_me=True,
                         checksum_address=idle_staker_account,
                         blockchain=testerchain)
    yield idle_staker


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
def funded_blockchain(testerchain, agency, token_economics, test_registry):

    # Who are ya'?
    deployer_address, *everyone_else, staking_participant = testerchain.client.accounts

    # Free ETH!!!
    testerchain.ether_airdrop(amount=DEVELOPMENT_ETH_AIRDROP_AMOUNT)

    # Free Tokens!!!
    token_airdrop(token_agent=NucypherTokenAgent(registry=test_registry),
                  origin=deployer_address,
                  addresses=everyone_else,
                  amount=token_economics.minimum_allowed_locked*5)

    # HERE YOU GO
    yield testerchain, deployer_address


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

    specification = b''.join((bytes(capsule),
                              bytes(ursula_pubkey),
                              bytes(ursula.decentralized_identity_evidence),
                              alice_address,
                              blockhash))

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
def instant_geth_dev_node():
    geth = NuCypherGethDevProcess()
    try:
        yield geth
    finally:
        if geth.is_running:
            geth.stop()
            assert not geth.is_running


@pytest.fixture(scope='session')
def stakeholder_config_file_location():
    path = os.path.join('/', 'tmp', 'nucypher-test-stakeholder.json')
    if os.path.exists(path):
        os.remove(path)
    yield path
    if os.path.exists(path):
        os.remove(path)


@pytest.fixture(scope='module')
def software_stakeholder(testerchain, agency, stakeholder_config_file_location, test_registry):
    token_agent, staking_agent, policy_agent = agency

    # Setup
    path = stakeholder_config_file_location
    if os.path.exists(path):
        os.remove(path)

    #                          0xaAa482c790b4301bE18D75A0D1B11B2ACBEF798B
    stakeholder_private_key = '255f64a948eeb1595b8a2d1e76740f4683eca1c8f1433d13293db9b6e27676cc'
    address = testerchain.provider.ethereum_tester.add_account(stakeholder_private_key,
                                                               password=INSECURE_DEVELOPMENT_PASSWORD)

    testerchain.provider.ethereum_tester.unlock_account(address, password=INSECURE_DEVELOPMENT_PASSWORD)

    tx = {'to': address,
          'from': testerchain.etherbase_account,
          'value': Web3.toWei('1', 'ether')}

    txhash = testerchain.client.w3.eth.sendTransaction(tx)
    _receipt = testerchain.wait_for_receipt(txhash)

    # Mock TransactingPower consumption (Etherbase)
    transacting_power = TransactingPower(account=testerchain.etherbase_account,
                                         password=INSECURE_DEVELOPMENT_PASSWORD)
    transacting_power.activate()

    token_agent.transfer(amount=NU(200_000, 'NU').to_nunits(),
                         sender_address=testerchain.etherbase_account,
                         target_address=address)

    # Create stakeholder from on-chain values given accounts over a web3 provider
    stakeholder = StakeHolder(registry=test_registry,
                              funding_account=address,
                              funding_password=INSECURE_DEVELOPMENT_PASSWORD,
                              trezor=False)

    # Teardown
    yield stakeholder
    if os.path.exists(path):
        os.remove(path)


@pytest.fixture(scope='module')
def manual_staker(testerchain, agency):
    token_agent, staking_agent, policy_agent = agency

    # 0xaaa23A5c74aBA6ca5E7c09337d5317A7C4563075
    staker_private_key = '13378db1c2af06933000504838afc2d52efa383206454deefb1836f8f4cd86f8'
    address = testerchain.provider.ethereum_tester.add_account(staker_private_key,
                                                               password=INSECURE_DEVELOPMENT_PASSWORD)

    tx = {'to': address,
          'from': testerchain.etherbase_account,
          'value': Web3.toWei('1', 'ether')}

    txhash = testerchain.client.w3.eth.sendTransaction(tx)
    _receipt = testerchain.wait_for_receipt(txhash)

    token_agent.transfer(amount=NU(200_000, 'NU').to_nunits(),
                         sender_address=testerchain.etherbase_account,
                         target_address=address)

    yield address


@pytest.fixture(scope='module')
def manual_worker(testerchain):
    worker_private_key = '4115115f4159db59a06327aa29544c417c52ddb80a4a26517367ff4514e0f694'
    address = testerchain.provider.ethereum_tester.add_account(worker_private_key,
                                                               password=INSECURE_DEVELOPMENT_PASSWORD)

    tx = {'to': address,
          'from': testerchain.etherbase_account,
          'value': Web3.toWei('1', 'ether')}

    txhash = testerchain.client.w3.eth.sendTransaction(tx)
    _receipt = testerchain.wait_for_receipt(txhash)
    yield address


#
# Test logging
#

@pytest.fixture(autouse=True, scope='function')
def log_in_and_out_of_test(request):
    test_name = request.node.name
    module_name = request.module.__name__
    test_logger.info(f"Starting {module_name}.py::{test_name}")
    yield
    test_logger.info(f"Finalized {module_name}.py::{test_name}")


@pytest.fixture(scope="module")
def deploy_contract(testerchain, test_registry):
    def wrapped(contract_name, *args, **kwargs):
        return testerchain.deploy_contract(testerchain.etherbase_account,
                                           test_registry,
                                           contract_name,
                                           *args,
                                           **kwargs)

    return wrapped
