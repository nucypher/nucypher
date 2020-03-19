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
import json
import os
import random
import tempfile
from typing import Union

import maya
import pytest
from eth_utils import to_checksum_address
from sqlalchemy.engine import create_engine
from twisted.logger import Logger
from umbral import pre
from umbral.curvebn import CurveBN
from umbral.keys import UmbralPrivateKey
from umbral.signing import Signer
from web3 import Web3

from nucypher.blockchain.economics import StandardTokenEconomics, BaseEconomics
from nucypher.blockchain.eth.actors import Staker, StakeHolder
from nucypher.blockchain.eth.agents import NucypherTokenAgent
from nucypher.blockchain.eth.clients import NuCypherGethDevProcess
from nucypher.blockchain.eth.constants import PREALLOCATION_ESCROW_CONTRACT_NAME
from nucypher.blockchain.eth.deployers import (NucypherTokenDeployer,
                                               StakingEscrowDeployer,
                                               PolicyManagerDeployer,
                                               AdjudicatorDeployer,
                                               StakingInterfaceDeployer,
                                               WorklockDeployer
)
from nucypher.blockchain.eth.interfaces import BlockchainInterfaceFactory
from nucypher.blockchain.eth.networks import NetworksInventory
from nucypher.blockchain.eth.registry import (
    InMemoryContractRegistry,
    RegistrySourceManager,
    BaseContractRegistry,
    LocalContractRegistry,
    IndividualAllocationRegistry,
    CanonicalRegistrySource
)
from nucypher.blockchain.eth.sol.compile import SolidityCompiler
from nucypher.blockchain.eth.token import NU
from nucypher.characters.lawful import Enrico, Bob
from nucypher.config.characters import AliceConfiguration
from nucypher.config.characters import (
    UrsulaConfiguration,
    BobConfiguration,
    StakeHolderConfiguration
)
from nucypher.crypto.powers import TransactingPower
from nucypher.crypto.utils import canonical_address_from_umbral_key
from nucypher.datastore import datastore
from nucypher.datastore.db import Base
from nucypher.policy.collections import IndisputableEvidence, WorkOrder
from nucypher.utilities.logging import GlobalLoggerSettings
from nucypher.utilities.sandbox.blockchain import token_airdrop, TesterBlockchain
from nucypher.utilities.sandbox.constants import (
    BASE_TEMP_PREFIX,
    BASE_TEMP_DIR,
    DATETIME_FORMAT,
    DEVELOPMENT_ETH_AIRDROP_AMOUNT,
    DEVELOPMENT_TOKEN_AIRDROP_AMOUNT,
    MIN_STAKE_FOR_TESTS,
    BONUS_TOKENS_FOR_TESTS,
    MOCK_POLICY_DEFAULT_M,
    MOCK_URSULA_STARTING_PORT,
    MOCK_REGISTRY_FILEPATH,
    NUMBER_OF_URSULAS_IN_DEVELOPMENT_NETWORK,
    TEMPORARY_DOMAIN,
    TEST_PROVIDER_URI,
    INSECURE_DEVELOPMENT_PASSWORD,
    TEST_GAS_LIMIT,
    INSECURE_DEPLOYMENT_SECRET_HASH,
)
from nucypher.utilities.sandbox.middleware import MockRestMiddleware
from nucypher.utilities.sandbox.middleware import MockRestMiddlewareForLargeFleetTests
from nucypher.utilities.sandbox.policy import generate_random_label
from nucypher.utilities.sandbox.ursula import make_decentralized_ursulas
from nucypher.utilities.sandbox.ursula import make_federated_ursulas
from tests.performance_mocks import mock_cert_storage, mock_cert_loading, mock_rest_app_creation, mock_cert_generation, \
    mock_secret_source, mock_remember_node, mock_verify_node, mock_record_fleet_state, mock_message_verification, \
    mock_keep_learning

test_logger = Logger("test-logger")
MIN_REWARD_RATE_RANGE = (5, 10, 15)


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
def test_datastore():
    engine = create_engine('sqlite:///:memory:')
    Base.metadata.create_all(engine)
    test_datastore = datastore.Datastore(engine)
    yield test_datastore


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
                                        domains={TEMPORARY_DOMAIN},
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
                                        domains={TEMPORARY_DOMAIN},
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
                                domains={TEMPORARY_DOMAIN},
                                network_middleware=MockRestMiddleware(),
                                known_nodes=federated_ursulas,
                                federated_only=True,
                                abort_on_learning_error=True,
                                save_metadata=False,
                                reload_metadata=False,)
    yield config
    config.cleanup()


@pytest.fixture(scope="module")
def alice_blockchain_test_config(blockchain_ursulas, testerchain, test_registry):
    config = AliceConfiguration(dev_mode=True,
                                domains={TEMPORARY_DOMAIN},
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
                              domains={TEMPORARY_DOMAIN},
                              network_middleware=MockRestMiddleware(),
                              start_learning_now=False,
                              abort_on_learning_error=True,
                              federated_only=True,
                              save_metadata=False,
                              reload_metadata=False,)
    yield config
    config.cleanup()


@pytest.fixture(scope="module")
def bob_blockchain_test_config(blockchain_ursulas, testerchain, test_registry):
    config = BobConfiguration(dev_mode=True,
                              domains={TEMPORARY_DOMAIN},
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
def idle_blockchain_policy(testerchain, blockchain_alice, blockchain_bob, token_economics):
    """
    Creates a Policy, in a manner typical of how Alice might do it, with a unique label
    """
    random_label = generate_random_label()
    days = token_economics.minimum_locked_periods // 2
    now = testerchain.w3.eth.getBlock(block_identifier='latest').timestamp
    expiration = maya.MayaDT(now).add(days=days-1)
    n = 3
    m = 2
    policy = blockchain_alice.create_policy(blockchain_bob,
                                            label=random_label,
                                            m=m, n=n,
                                            value=n * days * 100,
                                            expiration=expiration)
    return policy


@pytest.fixture(scope="module")
def enacted_blockchain_policy(idle_blockchain_policy, blockchain_ursulas):
    # Alice has a policy in mind and knows of enough qualified Ursulas; she crafts an offer for them.

    # value and expiration were set when creating idle_blockchain_policy already
    # cannot set them again
    # deposit = NON_PAYMENT(b"0000000")
    # contract_end_datetime = maya.now() + datetime.timedelta(days=5)
    network_middleware = MockRestMiddleware()

    idle_blockchain_policy.make_arrangements(
        network_middleware, handpicked_ursulas=list(blockchain_ursulas))

    idle_blockchain_policy.enact(network_middleware)  # REST call happens here, as does population of TreasureMap.
    return idle_blockchain_policy


@pytest.fixture(scope="module")
def capsule_side_channel(enacted_federated_policy):
    class _CapsuleSideChannel:
        def __init__(self):
            self.reset()

        def __call__(self):
            message = "Welcome to flippering number {}.".format(len(self.messages)).encode()
            message_kit, _signature = self.enrico.encrypt_message(message)
            self.messages.append((message_kit, self.enrico))
            if self.plaintext_passthrough:
                self.plaintexts.append(message)
            return message_kit

        def reset(self, plaintext_passthrough=False):
            self.enrico = Enrico(policy_encrypting_key=enacted_federated_policy.public_key)
            self.messages = []
            self.plaintexts = []
            self.plaintext_passthrough = plaintext_passthrough
            return self(), self.enrico

    return _CapsuleSideChannel()


@pytest.fixture(scope="module")
def capsule_side_channel_blockchain(enacted_blockchain_policy):
    class _CapsuleSideChannel:
        def __init__(self):
            self.reset()

        def __call__(self):
            message = "Welcome to flippering number {}.".format(len(self.messages)).encode()
            message_kit, _signature = self.enrico.encrypt_message(message)
            self.messages.append((message_kit, self.enrico))
            if self.plaintext_passthrough:
                self.plaintexts.append(message)
            return message_kit

        def reset(self, plaintext_passthrough=False):
            self.enrico = Enrico(policy_encrypting_key=enacted_blockchain_policy.public_key)
            self.messages = []
            self.plaintexts = []
            self.plaintext_passthrough = plaintext_passthrough
            return self(), self.enrico

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

@pytest.fixture(scope='module')
def token_economics(testerchain):

    # Get current blocktime
    blockchain = BlockchainInterfaceFactory.get_interface(provider_uri=testerchain.provider_uri)
    now = blockchain.w3.eth.getBlock(block_identifier='latest').timestamp

    # Calculate instant start time
    one_hour_in_seconds = (60 * 60)
    start_date = now
    bidding_start_date = start_date

    # Ends in one hour
    bidding_end_date = start_date + one_hour_in_seconds
    cancellation_end_date = bidding_end_date + one_hour_in_seconds

    economics = StandardTokenEconomics(
        worklock_boosting_refund_rate=200,
        worklock_commitment_duration=60,  # periods
        worklock_supply=10*BaseEconomics._default_maximum_allowed_locked,
        bidding_start_date=bidding_start_date,
        bidding_end_date=bidding_end_date,
        cancellation_end_date=cancellation_end_date,
        worklock_min_allowed_bid=Web3.toWei(1, "ether")
    )
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
    # Monkey patch to prevent gas adjustment
    import eth
    eth._utils.headers.GAS_LIMIT_MINIMUM = TEST_GAS_LIMIT
    eth._utils.headers.GENESIS_GAS_LIMIT = TEST_GAS_LIMIT
    eth.vm.forks.frontier.headers.GENESIS_GAS_LIMIT = TEST_GAS_LIMIT

    # Monkey patch to prevent gas estimates
    def _get_buffered_gas_estimate(web3, transaction, gas_buffer=100000):
        return TEST_GAS_LIMIT

    import web3
    web3.eth.get_buffered_gas_estimate = _get_buffered_gas_estimate

    # Create the blockchain
    testerchain = TesterBlockchain(eth_airdrop=True, free_transactions=True)

    BlockchainInterfaceFactory.register_interface(interface=testerchain, force=True)

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

    # Reset chain state
    pyevm_backend = testerchain.provider.ethereum_tester.backend
    snapshot = pyevm_backend.chain.get_canonical_block_by_number(0).hash
    pyevm_backend.revert_to_snapshot(snapshot)

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


def _make_agency(testerchain, test_registry, token_economics):
    """
    Launch the big three contracts on provided chain,
    make agents for each and return them.
    """

    # Mock TransactingPower Consumption (Deployer)
    testerchain.transacting_power = TransactingPower(password=INSECURE_DEVELOPMENT_PASSWORD,
                                                     account=testerchain.etherbase_account)
    testerchain.transacting_power.activate()

    origin = testerchain.etherbase_account

    token_deployer = NucypherTokenDeployer(deployer_address=origin,
                                           economics=token_economics,
                                           registry=test_registry)
    token_deployer.deploy()

    staking_escrow_deployer = StakingEscrowDeployer(deployer_address=origin,
                                                    economics=token_economics,
                                                    registry=test_registry,
                                                    test_mode=True)
    staking_escrow_deployer.deploy(secret_hash=INSECURE_DEPLOYMENT_SECRET_HASH)

    policy_manager_deployer = PolicyManagerDeployer(deployer_address=origin,
                                                    economics=token_economics,
                                                    registry=test_registry)
    policy_manager_deployer.deploy(secret_hash=INSECURE_DEPLOYMENT_SECRET_HASH)

    adjudicator_deployer = AdjudicatorDeployer(deployer_address=origin,
                                               economics=token_economics,
                                               registry=test_registry)
    adjudicator_deployer.deploy(secret_hash=INSECURE_DEPLOYMENT_SECRET_HASH)

    staking_interface_deployer = StakingInterfaceDeployer(deployer_address=origin,
                                                          economics=token_economics,
                                                          registry=test_registry)
    staking_interface_deployer.deploy(secret_hash=INSECURE_DEPLOYMENT_SECRET_HASH)

    worklock_deployer = WorklockDeployer(deployer_address=origin,
                                         economics=token_economics,
                                         registry=test_registry)
    worklock_deployer.deploy()

    token_agent = token_deployer.make_agent()                           # 1 Token
    staking_agent = staking_escrow_deployer.make_agent()                # 2 Staking Escrow
    policy_agent = policy_manager_deployer.make_agent()                 # 3 Policy Agent
    _adjudicator_agent = adjudicator_deployer.make_agent()              # 4 Adjudicator
    _worklock_agent = worklock_deployer.make_agent()                    # 5 Worklock

    # Set additional parameters
    minimum, default, maximum = MIN_REWARD_RATE_RANGE
    txhash = policy_agent.contract.functions.setMinRewardRateRange(minimum, default, maximum).transact()
    _receipt = testerchain.wait_for_receipt(txhash)

    # TODO: Get rid of returning these agents here.
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


@pytest.fixture(scope='module', autouse=True)
def test_registry_source_manager(testerchain, test_registry):

    class MockRegistrySource(CanonicalRegistrySource):
        name = "Mock Registry Source"
        is_primary = False

        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            if self.network != TEMPORARY_DOMAIN:
                raise ValueError(f"Somehow, MockRegistrySource is trying to get a registry for '{self.network}'. "
                                 f"Only '{TEMPORARY_DOMAIN}' is supported.'")
            factory = testerchain.get_contract_factory(contract_name=PREALLOCATION_ESCROW_CONTRACT_NAME)
            preallocation_escrow_abi = factory.abi
            self.allocation_template = {
                "BENEFICIARY_ADDRESS": ["ALLOCATION_CONTRACT_ADDRESS", preallocation_escrow_abi]
            }

        def get_publication_endpoint(self) -> str:
            return f":mock-registry-source:/{self.network}/{self.registry_name}"

        def fetch_latest_publication(self) -> Union[str, bytes]:
            self.logger.debug(f"Reading registry at {self.get_publication_endpoint()}")
            if self.registry_name == BaseContractRegistry.REGISTRY_NAME:
                registry_data = test_registry.read()
            elif self.registry_name == IndividualAllocationRegistry.REGISTRY_NAME:
                registry_data = self.allocation_template
            raw_registry_data = json.dumps(registry_data)
            return raw_registry_data

    RegistrySourceManager._FALLBACK_CHAIN = (MockRegistrySource,)
    NetworksInventory.NETWORKS = (TEMPORARY_DOMAIN,)


@pytest.fixture(scope='module')
def agency(testerchain, test_registry, token_economics, test_registry_source_manager):
    agents = _make_agency(testerchain=testerchain,
                          test_registry=test_registry,
                          token_economics=token_economics)
    yield agents


@pytest.fixture(scope='module')
def agency_local_registry(testerchain, agency, test_registry):
    registry = LocalContractRegistry(filepath=MOCK_REGISTRY_FILEPATH)
    registry.write(test_registry.read())
    yield registry
    if os.path.exists(MOCK_REGISTRY_FILEPATH):
        os.remove(MOCK_REGISTRY_FILEPATH)


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

        amount = MIN_STAKE_FOR_TESTS + random.randrange(BONUS_TOKENS_FOR_TESTS)

        # for a random lock duration
        min_locktime, max_locktime = token_economics.minimum_locked_periods, token_economics.maximum_rewarded_periods
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
    for u in _ursulas:
        u.synchronous_query_timeout = .01  # We expect to never have to wait for content that is actually on-chain during tests.
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
                  amount=token_economics.minimum_allowed_locked * 5)

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
    task = WorkOrder.PRETask(capsule, task_signature, cfrag, cfrag_signature)
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
    stakeholder = StakeHolder(registry=test_registry, initial_address=address)

    # Teardown
    yield stakeholder
    if os.path.exists(path):
        os.remove(path)


@pytest.fixture(scope="module")
def stakeholder_configuration(testerchain, agency_local_registry):
    config = StakeHolderConfiguration(provider_uri=testerchain.provider_uri,
                                      registry_filepath=agency_local_registry.filepath)
    return config


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
    worker_private_key = os.urandom(32).hex()
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


@pytest.fixture(scope='module')
def get_random_checksum_address():
    def _get_random_checksum_address():
        canonical_address = os.urandom(20)
        checksum_address = to_checksum_address(canonical_address)
        return checksum_address

    return _get_random_checksum_address


@pytest.fixture(scope='module')
def mock_transacting_power_activation(testerchain):
    def _mock_transacting_power_activation(password, account):
        testerchain.transacting_power = TransactingPower(password=password, account=account)
        testerchain.transacting_power.activate()

    return _mock_transacting_power_activation


@pytest.fixture(scope="module")
def fleet_of_highperf_mocked_ursulas(ursula_federated_test_config, request):
    try:
        quantity = request.param
    except AttributeError:
        quantity = 5000  # Bigass fleet by default; that's kinda the point.
    with GlobalLoggerSettings.pause_all_logging_while():
        with mock_secret_source():
            with mock_cert_storage, mock_cert_loading, mock_rest_app_creation, mock_cert_generation, mock_remember_node, mock_message_verification:
                _ursulas = make_federated_ursulas(ursula_config=ursula_federated_test_config,
                                                  quantity=quantity, know_each_other=False)
                all_ursulas = {u.checksum_address: u for u in _ursulas}
                for ursula in _ursulas:
                    ursula.known_nodes._nodes = all_ursulas
                    ursula.known_nodes.checksum = b"This is a fleet state checksum..".hex()
    return _ursulas


@pytest.fixture(scope="module")
def highperf_mocked_alice(fleet_of_highperf_mocked_ursulas):
    config = AliceConfiguration(dev_mode=True,
                                domains={TEMPORARY_DOMAIN},
                                network_middleware=MockRestMiddlewareForLargeFleetTests(),
                                federated_only=True,
                                abort_on_learning_error=True,
                                save_metadata=False,
                                reload_metadata=False)

    with mock_cert_storage, mock_verify_node, mock_record_fleet_state, mock_message_verification, mock_keep_learning:
        alice = config.produce(known_nodes=list(fleet_of_highperf_mocked_ursulas)[:1])
    return alice


@pytest.fixture(scope="module")
def highperf_mocked_bob(fleet_of_highperf_mocked_ursulas):
    config = BobConfiguration(dev_mode=True,
                              domains={TEMPORARY_DOMAIN},
                              network_middleware=MockRestMiddlewareForLargeFleetTests(),
                              federated_only=True,
                              abort_on_learning_error=True,
                              save_metadata=False,
                              reload_metadata=False)

    with mock_cert_storage, mock_verify_node, mock_record_fleet_state:
        bob = config.produce(known_nodes=list(fleet_of_highperf_mocked_ursulas)[:1])
    return bob