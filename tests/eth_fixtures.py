import os
import shutil
import signal
import subprocess
import tempfile
import time
from os.path import abspath, dirname

import pytest
from constant_sorrow import constants
from eth_tester import EthereumTester
from geth import LoggingMixin, DevGethProcess
from web3 import EthereumTesterProvider, IPCProvider

from nucypher.blockchain.eth.agents import NucypherTokenAgent, MinerAgent
from nucypher.blockchain.eth.chains import TesterBlockchain
from nucypher.blockchain.eth.deployers import PolicyManagerDeployer, NucypherTokenDeployer, MinerEscrowDeployer
from nucypher.blockchain.eth.interfaces import EthereumContractRegistrar, DeployerCircumflex
from nucypher.blockchain.eth.sol.compile import SolidityCompiler
from tests.blockchain.eth import contracts
from tests.blockchain.eth.utilities import MockMinerEscrowDeployer, TesterPyEVMBackend, MockNucypherTokenDeployer

constants.NUMBER_OF_TEST_ETH_ACCOUNTS(10)



#
# Provider Fixtures
#


@pytest.fixture(scope='session')
def manual_geth_ipc_provider():
    """
    Provider backend
    https:// github.com/ethereum/eth-tester
    """
    ipc_provider = IPCProvider(ipc_path='/tmp/geth.ipc')
    yield ipc_provider


@pytest.fixture(scope='session')
def auto_geth_dev_ipc_provider():
    """
    Provider backend
    https:// github.com/ethereum/eth-tester
    """
    # TODO: logging
    geth_cmd = ["geth --dev"]  # WARNING: changing this may have undesireable effects.
    geth_process = subprocess.Popen(geth_cmd, stdout=subprocess.PIPE, shell=True, preexec_fn=os.setsid)

    time.sleep(10)  #TODO: better wait with file socket

    ipc_provider = IPCProvider(ipc_path=os.path.join('/tmp/geth.ipc'))

    yield ipc_provider
    os.killpg(os.getpgid(geth_process.pid), signal.SIGTERM)


@pytest.fixture(scope='session')
def auto_geth_ipc_provider():
    """
    Provider backend
    https: // github.com / ethereum / eth - tester     # available-backends
    """

    #
    # spin-up geth
    #

    class IPCDevGethProcess(LoggingMixin, DevGethProcess):
        data_dir = tempfile.mkdtemp()
        chain_name = 'tester'
        ipc_path = os.path.join(data_dir, chain_name, 'geth.ipc')

        def __init__(self, *args, **kwargs):
            super().__init__(chain_name=self.chain_name,
                             base_dir=self.data_dir,
                             *args, **kwargs)

    geth = IPCDevGethProcess()
    geth.start()

    geth.wait_for_ipc(timeout=30)
    geth.wait_for_dag(timeout=600)  # 10 min
    assert geth.is_dag_generated
    assert geth.is_running
    assert geth.is_alive

    ipc_provider = IPCProvider(ipc_path=geth.ipc_path)
    yield ipc_provider

    #
    # Teardown
    #
    geth.stop()
    assert geth.is_stopped
    assert not geth.is_alive
    shutil.rmtree(geth.data_dir)



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

    # create a temporary registrar for the tester blockchain
    _, filepath = tempfile.mkstemp()
    test_registrar = EthereumContractRegistrar(chain_name='tester', registrar_filepath=filepath)

    # Configure a custom provider
    overrides = {'gas_limit': 4626271}
    pyevm_backend = TesterPyEVMBackend(genesis_overrides=overrides)

    # pyevm_backend = PyEVMBackend() # TODO: Remove custom overrides?

    eth_tester = EthereumTester(backend=pyevm_backend, auto_mine_transactions=True)
    pyevm_provider = EthereumTesterProvider(ethereum_tester=eth_tester)

    # Use the the custom provider and registrar to init an interface
    circumflex = DeployerCircumflex(compiler=solidity_compiler,    # freshly recompile
                                    registrar=test_registrar,      # use temporary registrar
                                    providers=(pyevm_provider, ))  # use custom test provider

    # Create the blockchain
    testerchain = TesterBlockchain(interface=circumflex, test_accounts=10)
    origin, *everyone = testerchain.interface.w3.eth.accounts
    circumflex.deployer_address = origin  # Set the deployer address from a freshly created test account

    yield testerchain

    testerchain.sever_connection()  # Destroy the blockchin singelton cache
    os.remove(filepath)             # remove registrar tempfile


#
# Utility
#

@pytest.fixture(scope='module')
def token_airdrop(testerchain, mock_token_agent):
    origin, *everybody_else = testerchain.interface.w3.eth.accounts
    mock_token_agent.token_airdrop(origin=origin,
                                   addresses=everybody_else,
                                   amount=100000*constants.M)
    yield


@pytest.fixture(scope='module')
def three_agents(testerchain):
    """
    Musketeers, if you will.
    Launch the big three contracts on provided chain,
    make agents for each and return them.
    """
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

    return token_agent, miner_agent, policy_manager_deployer.make_agent()


# 
# Deployers #
# 


@pytest.fixture(scope='module')
def mock_token_deployer(testerchain):
    origin, *everybody_else = testerchain.interface.w3.eth.accounts
    token_deployer = MockNucypherTokenDeployer(blockchain=testerchain, deployer_address=origin)
    token_deployer.arm()
    token_deployer.deploy()
    yield token_deployer


@pytest.fixture(scope='module')
def mock_miner_escrow_deployer(testerchain, mock_token_agent):
    origin, *everybody_else = testerchain.interface.w3.eth.accounts
    escrow = MockMinerEscrowDeployer(token_agent=mock_token_agent, deployer_address=origin)
    escrow.arm()
    escrow.deploy()
    yield escrow


@pytest.fixture(scope='module')
def mock_policy_manager_deployer(testerchain, mock_miner_agent):
    origin, *everybody_else = testerchain.interface.w3.eth.accounts
    policy_manager_deployer = PolicyManagerDeployer(miner_agent=mock_miner_agent, deployer_address=origin)
    policy_manager_deployer.arm()
    policy_manager_deployer.deploy()
    yield policy_manager_deployer


#
# Agents #
#

@pytest.fixture(scope='module')
def mock_token_agent(mock_token_deployer):
    token_agent = mock_token_deployer.make_agent()
    assert mock_token_deployer.contract.address == token_agent.contract_address
    yield token_agent


@pytest.fixture(scope='module')
@pytest.mark.usefixtures("mock_token_agent")
def mock_miner_agent(mock_miner_escrow_deployer):
    miner_agent = mock_miner_escrow_deployer.make_agent()
    assert mock_miner_escrow_deployer.contract.address == miner_agent.contract_address
    yield miner_agent


@pytest.fixture(scope='module')
@pytest.mark.usefixtures("mock_miner_agent")
def mock_policy_agent(mock_policy_manager_deployer):
    policy_agent = mock_policy_manager_deployer.make_agent()
    assert mock_policy_manager_deployer.contract.address == policy_agent.contract_address
    yield policy_agent


#
# Actors
#

@pytest.fixture(scope='module')
@pytest.mark.usefixtures("mock_policy_agent")
def miners(testerchain, mock_miner_agent, mock_token_agent):
    mock_token_agent.blockchain.ether_airdrop(amount=10000)

    origin, *everybody_else = testerchain.interface.w3.eth.accounts
    mock_token_agent.token_airdrop(origin=origin,
                                   addresses=everybody_else,
                                   amount=100000*constants.M)
    mock_miner_agent.blockchain.time_travel(periods=1)

    miners = mock_miner_agent.spawn_random_miners(addresses=everybody_else)
    testerchain.time_travel(periods=1)
    yield miners
