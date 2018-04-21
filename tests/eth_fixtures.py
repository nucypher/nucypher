import os
import signal
import subprocess
import tempfile

import pytest
import shutil
import time
from eth_tester import EthereumTester, PyEVMBackend
from geth import LoggingMixin, DevGethProcess
from os.path import abspath, dirname
from tests.blockchain.eth.utilities import MockMinerEscrowDeployer
from web3 import EthereumTesterProvider, IPCProvider, Web3
from web3.middleware import geth_poa_middleware

from nkms.blockchain.eth.agents import NuCypherKMSTokenAgent, MinerAgent
from nkms.blockchain.eth.agents import PolicyAgent
from nkms.blockchain.eth.chains import TheBlockchain, TesterBlockchain
from nkms.blockchain.eth.deployers import PolicyManagerDeployer, NuCypherKMSTokenDeployer
from nkms.blockchain.eth.interfaces import Registrar, ContractProvider
from nkms.blockchain.eth.sol.compile import SolidityCompiler
from tests.blockchain.eth import contracts, utilities


#
# Session fixtures
#

@pytest.fixture(scope='session')
def solidity_compiler():
    test_contracts_dir = os.path.join(dirname(abspath(contracts.__file__)), 'contracts')
    compiler = SolidityCompiler(test_contract_dir=test_contracts_dir)
    yield compiler

#
# Web3 provider backends
#


@pytest.fixture(scope='session')
def manual_geth_dev_ipc_provider():
    """
    Provider backend
    https:// github.com/ethereum/eth-tester
    """
    ipc_provider = IPCProvider(ipc_path=os.path.join('/tmp/geth.ipc'))
    tester_provider = ContractProvider(provider_backend=ipc_provider,
                                       registrar=registrar,
                                       sol_compiler=solidity_compiler)
    yield ipc_provider


@pytest.fixture(scope='session')
def auto_geth_dev_ipc_provider():
    """
    Provider backend
    https:// github.com/ethereum/eth-tester
    """
    geth_cmd = ["geth --dev"]  # WARNING: changing this may have undesireable effects.
    geth_process = subprocess.Popen(geth_cmd, stdout=subprocess.PIPE, shell=True, preexec_fn=os.setsid)

    time.sleep(2)  #TODO: better wait with file socket

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

    testing_dir = tempfile.mkdtemp()
    chain_name = 'nkms_tester'

    class NKMSGeth(LoggingMixin, DevGethProcess):
        pass

    geth = DevGethProcess(chain_name=chain_name, base_dir=testing_dir)
    geth.start()

    geth.wait_for_ipc(timeout=30)
    geth.wait_for_dag(timeout=120)
    assert geth.is_dag_generated
    assert geth.is_running
    assert geth.is_alive

    ipc_provider = IPCProvider(ipc_path=os.path.join(testing_dir, chain_name, 'geth.ipc'))

    yield ipc_provider

    #
    # Teardown
    #
    geth.stop()
    assert geth.is_stopped
    assert not geth.is_alive
    shutil.rmtree(testing_dir)


@pytest.fixture(scope='session')
def pyevm_provider():
    """
    Provider backend
    https: // github.com / ethereum / eth - tester     # available-backends
    """
    # TODO:     # eth_tester.backend.chain.header.gas_limit = 4626271
    eth_tester = EthereumTester(backend=PyEVMBackend(), auto_mine_transactions=True)
    pyevm_provider = EthereumTesterProvider(ethereum_tester=eth_tester)
    yield pyevm_provider


@pytest.fixture(scope='session')
def web3(auto_geth_dev_ipc_provider):

    w3 = Web3(providers=auto_geth_dev_ipc_provider)
    w3.middleware_stack.inject(geth_poa_middleware, layer=0)

    assert len(w3.eth.accounts) == 1
    _txhashes = utilities.generate_accounts(w3=w3, quantity=9)
    assert len(w3.eth.accounts) == 10

    yield w3


#
# Module Fixtures
#

@pytest.fixture(scope='module')
def contract_provider(web3, registrar, solidity_compiler):
    tester_provider = ContractProvider(provider_backend=web3, registrar=registrar, sol_compiler=solidity_compiler)
    yield tester_provider


@pytest.fixture(scope='module')
def registrar():
    _, filepath = tempfile.mkstemp()
    registrar = Registrar(chain_name='tester', registrar_filepath=filepath)
    yield registrar
    os.remove(filepath)


@pytest.fixture(scope='module')
def chain(contract_provider):
    chain = TesterBlockchain(contract_provider=contract_provider)
    yield chain

    del chain
    TheBlockchain._TheBlockchain__instance = None


# 
# API #
# 


@pytest.fixture()
def mock_token_deployer(chain):
    token_deployer = NuCypherKMSTokenDeployer(blockchain=chain)
    token_deployer.arm()
    token_deployer.deploy()
    yield token_deployer


@pytest.fixture()
def mock_miner_escrow_deployer(token_agent):
    escrow = MockMinerEscrowDeployer(token_agent=token_agent)
    escrow.arm()
    escrow.deploy()
    yield escrow


@pytest.fixture()
def mock_policy_manager_deployer(mock_miner_escrow_deployer):
    policy_manager_deployer = PolicyManagerDeployer(miner_agent=mock_token_deployer)
    policy_manager_deployer.arm()
    policy_manager_deployer.deploy()
    yield policy_manager_deployer


#
# Unused args preserve fixture dependency order #
#

@pytest.fixture()
def token_agent(chain, mock_token_deployer):
    token = NuCypherKMSTokenAgent(blockchain=chain)
    yield token


@pytest.fixture()
def mock_miner_agent(token_agent, mock_token_deployer, mock_miner_escrow_deployer):
    miner_agent = MinerAgent(token_agent=token_agent)
    yield miner_agent


@pytest.fixture()
def mock_policy_agent(mock_miner_agent, token_agent, mock_token_deployer, mock_miner_escrow_deployer):
    policy_agent = PolicyAgent(miner_agent=mock_miner_agent)
    yield policy_agent
