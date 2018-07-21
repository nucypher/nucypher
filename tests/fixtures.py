import contextlib

import datetime
import maya
import os
import pytest
import tempfile
from constant_sorrow import constants
from eth_tester import EthereumTester
from eth_utils import to_checksum_address
from os.path import abspath, dirname
from sqlalchemy.engine import create_engine
from web3 import EthereumTesterProvider

from nucypher.blockchain.eth.chains import TesterBlockchain
from nucypher.blockchain.eth.deployers import PolicyManagerDeployer, NucypherTokenDeployer, MinerEscrowDeployer
from nucypher.blockchain.eth.interfaces import DeployerCircumflex
from nucypher.blockchain.eth.sol.compile import SolidityCompiler
from nucypher.blockchain.eth.utilities import OverridablePyEVMBackend, TemporaryEthereumContractRegistry
from nucypher.characters import Alice, Bob
from nucypher.data_sources import DataSource
from nucypher.keystore import keystore
from nucypher.keystore.db import Base
from nucypher.keystore.keypairs import SigningKeypair
from tests.blockchain.eth import contracts
from tests.blockchain.eth.utilities import token_airdrop
from tests.utilities.blockchain import make_ursulas
from tests.utilities.network import MockRestMiddleware

#
# Setup
#


constants.NUMBER_OF_TEST_ETH_ACCOUNTS(10)


@pytest.fixture(scope="function")
def tempfile_path():
    """
    User is responsible for closing the file given at the path.
    """
    fd, path = tempfile.mkstemp()
    yield path
    os.close(fd)
    os.remove(path)


@pytest.fixture(scope="module")
def test_keystore():
    engine = create_engine('sqlite:///:memory:')
    Base.metadata.create_all(engine)
    test_keystore = keystore.KeyStore(engine)
    yield test_keystore



#
# Policies
#


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
def enacted_federated_policy(idle_federated_policy, ursulas):
    # Alice has a policy in mind and knows of enough qualifies Ursulas; she crafts an offer for them.
    deposit = constants.NON_PAYMENT(b"0000000")
    contract_end_datetime = maya.now() + datetime.timedelta(days=5)
    network_middleware = MockRestMiddleware()

    idle_federated_policy.make_arrangements(network_middleware,
                                            deposit=deposit,
                                            expiration=contract_end_datetime,
                                            handpicked_ursulas=ursulas)
    idle_federated_policy.enact(network_middleware)  # REST call happens here, as does population of TreasureMap.

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
def enacted_blockchain_policy(idle_blockchain_policy, ursulas):
    # Alice has a policy in mind and knows of enough qualifies Ursulas; she crafts an offer for them.
    deposit = constants.NON_PAYMENT(b"0000000")
    contract_end_datetime = maya.now() + datetime.timedelta(days=5)
    network_middleware = MockRestMiddleware()

    idle_blockchain_policy.make_arrangements(network_middleware, deposit=deposit, expiration=contract_end_datetime,
                                             ursulas=list(ursulas))
    idle_blockchain_policy.enact(network_middleware)  # REST call happens here, as does population of TreasureMap.

    return idle_blockchain_policy


#
# Alice, Bob, and Capsule
#

@pytest.fixture(scope="module")
def alice(ursulas):
    alice = Alice(network_middleware=MockRestMiddleware(),
                  known_nodes=ursulas,
                  federated_only=True,
                  abort_on_learning_error=True)
    alice.recruit = lambda *args, **kwargs: [u._ether_address for u in ursulas]

    return alice


@pytest.fixture(scope="module")
def blockchain_alice(mining_ursulas, three_agents):
    token_agent, miner_agent, policy_agent = three_agents
    etherbase, alice_address, bob_address, *everyone_else = token_agent.blockchain.interface.w3.eth.accounts

    alice = Alice(network_middleware=MockRestMiddleware(),
                  policy_agent=policy_agent,
                  known_nodes=mining_ursulas,
                  abort_on_learning_error=True,
                  checksum_address=alice_address)
    # alice.recruit = lambda *args, **kwargs: [u._ether_address for u in ursulas]

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
def ursulas(three_agents):
    token_agent, miner_agent, policy_agent = three_agents
    ether_addresses = [to_checksum_address(os.urandom(20)) for _ in range(constants.NUMBER_OF_URSULAS_IN_NETWORK)]
    _ursulas = make_ursulas(ether_addresses=ether_addresses,
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
def non_ursula_miners(three_agents):
    token_agent, miner_agent, policy_agent = three_agents
    etherbase, alice, bob, *all_yall = token_agent.blockchain.interface.w3.eth.accounts

    ursula_addresses = all_yall[:int(constants.NUMBER_OF_URSULAS_IN_NETWORK)]

    _receipts = token_airdrop(token_agent=token_agent,
                              origin=etherbase,
                              addresses=all_yall,
                              amount=1000000*constants.M)

    starting_point = constants.URSULA_PORT_SEED + 500

    _ursulas = make_ursulas(ether_addresses=ursula_addresses,
                            miner_agent=miner_agent,
                            miners=True,
                            bare=True)
    try:
        yield _ursulas
    finally:
        # Remove the DBs that have been sprayed hither and yon.
        with contextlib.suppress(FileNotFoundError):
            for port, ursula in enumerate(_ursulas, start=int(starting_point)):
                os.remove("test-{}".format(port))


#
# Blockchain
#

@pytest.fixture(scope='session')
def solidity_compiler():
    """Doing this more than once per session will result in slower test run times."""
    test_contracts_dir = os.path.join(dirname(abspath(contracts.__file__)), 'contracts')
    compiler = SolidityCompiler(test_contract_dir=test_contracts_dir)
    yield compiler


@pytest.fixture(scope='module')
def testerchain(solidity_compiler):
    """
    https: // github.com / ethereum / eth - tester     # available-backends
    """

    temp_registrar = TemporaryEthereumContractRegistry()

    # Configure a custom provider
    overrides = {'gas_limit': 4626271}
    pyevm_backend = OverridablePyEVMBackend(genesis_overrides=overrides)

    eth_tester = EthereumTester(backend=pyevm_backend, auto_mine_transactions=True)
    pyevm_provider = EthereumTesterProvider(ethereum_tester=eth_tester)

    test_providers = (pyevm_provider, )

    # Use the the custom provider and registrar to init an interface
    circumflex = DeployerCircumflex(compiler=solidity_compiler,    # freshly recompile if not None
                                    registry=temp_registrar,
                                    providers=test_providers)

    # Create the blockchain
    testerchain = TesterBlockchain(interface=circumflex, test_accounts=10)
    origin, *everyone = testerchain.interface.w3.eth.accounts
    circumflex.deployer_address = origin  # Set the deployer address from a freshly created test account

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

    miner_escrow_deployer = MinerEscrowDeployer(token_agent=token_agent, deployer_address=origin)
    miner_escrow_deployer.arm()
    miner_escrow_deployer.deploy()

    miner_agent = miner_escrow_deployer.make_agent()

    policy_manager_deployer = PolicyManagerDeployer(miner_agent=miner_agent, deployer_address=origin)
    policy_manager_deployer.arm()
    policy_manager_deployer.deploy()

    policy_agent = policy_manager_deployer.make_agent()

    return token_agent, miner_agent, policy_agent
