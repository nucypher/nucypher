import os
import signal
import subprocess
import tempfile

import pytest
import shutil
import time
from eth_tester import EthereumTester
from geth import LoggingMixin, DevGethProcess
from os.path import abspath, dirname
from web3 import EthereumTesterProvider, IPCProvider

from nucypher.blockchain.eth.deployers import PolicyManagerDeployer
from nucypher.blockchain.eth.interfaces import Registrar
from nucypher.blockchain.eth.sol.compile import SolidityCompiler
from nucypher.config.configs import BlockchainConfig
from tests.blockchain.eth import contracts, utilities
from tests.blockchain.eth.utilities import MockMinerEscrowDeployer, TesterPyEVMBackend, MockNucypherTokenDeployer


#
# Provider Fixtures
#


@pytest.fixture(scope='session')
def manual_geth_ipc_provider():
    """
    Provider backend
    https:// github.com/ethereum/eth-tester
    """
    ipc_provider = IPCProvider(ipc_path=os.path.join('/tmp/geth.ipc'))
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


@pytest.fixture(scope='module')
def pyevm_provider():
    """
    Test provider backend
    https: // github.com / ethereum / eth - tester     # available-backends
    """
    overrides = {'gas_limit': 4626271}
    pyevm_backend = TesterPyEVMBackend(genesis_overrides=overrides)

    # pyevm_backend = PyEVMBackend()

    eth_tester = EthereumTester(backend=pyevm_backend, auto_mine_transactions=True)
    pyevm_provider = EthereumTesterProvider(ethereum_tester=eth_tester)

    yield pyevm_provider


#
# Blockchain Fixtures
#


@pytest.fixture(scope='session')
def solidity_compiler():
    test_contracts_dir = os.path.join(dirname(abspath(contracts.__file__)), 'contracts')
    compiler = SolidityCompiler(test_contract_dir=test_contracts_dir)
    yield compiler


@pytest.fixture(scope='module')
def registrar():
    _, filepath = tempfile.mkstemp()
    test_registrar = Registrar(chain_name='tester', registrar_filepath=filepath)
    yield test_registrar
    os.remove(filepath)


@pytest.fixture(scope='module')
def blockchain_config(pyevm_provider, solidity_compiler, registrar):
    BlockchainConfig.add_provider(pyevm_provider)
    config = BlockchainConfig(compiler=solidity_compiler, registrar=registrar, deploy=True, tester=True)  # TODO: pass in address
    yield config
    config.chain.sever()
    del config


@pytest.fixture(scope='module')
def deployer_interface(blockchain_config):
    interface = blockchain_config.chain.interface
    w3 = interface.w3

    if len(w3.eth.accounts) == 1:
        utilities.generate_accounts(w3=w3, quantity=9)
    assert len(w3.eth.accounts) == 10

    yield interface


@pytest.fixture(scope='module')
def web3(deployer_interface):
    """Compadibility fixture"""
    return deployer_interface.w3


@pytest.fixture(scope='module')
def chain(deployer_interface, airdrop_ether=False):
    chain = deployer_interface.blockchain_config.chain

    if airdrop_ether:
        one_million_ether = 10 ** 6 * 10 ** 18  # wei -> ether
        chain.ether_airdrop(amount=one_million_ether)

    yield chain

# 
# Deployers #
# 


@pytest.fixture(scope='module')
def mock_token_deployer(chain):
    origin, *everyone = chain.interface.w3.eth.coinbase
    token_deployer = MockNucypherTokenDeployer(blockchain=chain, deployer_address=origin)
    token_deployer.arm()
    token_deployer.deploy()
    yield token_deployer


@pytest.fixture(scope='module')
def mock_miner_escrow_deployer(mock_token_agent):
    escrow = MockMinerEscrowDeployer(token_agent=mock_token_agent)
    escrow.arm()
    escrow.deploy()
    yield escrow


@pytest.fixture(scope='module')
def mock_policy_manager_deployer(mock_miner_agent):
    policy_manager_deployer = PolicyManagerDeployer(miner_agent=mock_miner_agent)
    policy_manager_deployer.arm()
    policy_manager_deployer.deploy()
    yield policy_manager_deployer


#
# Agents #
# Unused args preserve fixture dependency order #
#

@pytest.fixture(scope='module')
def mock_token_agent(mock_token_deployer):
    token_agent = mock_token_deployer.make_agent()

    assert mock_token_deployer._contract.address == token_agent.contract_address
    yield token_agent


@pytest.fixture(scope='module')
def mock_miner_agent(mock_miner_escrow_deployer):
    miner_agent = mock_miner_escrow_deployer.make_agent()

    assert mock_miner_escrow_deployer._contract.address == miner_agent.contract_address
    yield miner_agent


@pytest.fixture(scope='module')
def mock_policy_agent(mock_policy_manager_deployer):
    policy_agent = mock_policy_manager_deployer.make_agent()

    assert mock_policy_manager_deployer._contract.address == policy_agent.contract_address
    yield policy_agent
