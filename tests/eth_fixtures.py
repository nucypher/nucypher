import contextlib
import os
import signal
import subprocess
import tempfile

import pytest
import shutil
import time
from constant_sorrow import constants
from eth_tester import EthereumTester
from geth import LoggingMixin, DevGethProcess
from os.path import abspath, dirname
from web3 import EthereumTesterProvider, IPCProvider

from nucypher.blockchain.eth.chains import TesterBlockchain
from nucypher.blockchain.eth.deployers import PolicyManagerDeployer, NucypherTokenDeployer, MinerEscrowDeployer
from nucypher.blockchain.eth.interfaces import DeployerCircumflex
from nucypher.blockchain.eth.sol.compile import SolidityCompiler
from nucypher.blockchain.eth.utilities import OverridablePyEVMBackend, TemporaryEthereumContractRegistry
from tests.blockchain.eth import contracts
from tests.blockchain.eth.utilities import token_airdrop
from tests.utilities import make_ursulas

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

    temp_registrar = TemporaryEthereumContractRegistry()

    # Configure a custom provider
    overrides = {'gas_limit': 4626271}
    pyevm_backend = OverridablePyEVMBackend(genesis_overrides=overrides)

    eth_tester = EthereumTester(backend=pyevm_backend, auto_mine_transactions=True)
    pyevm_provider = EthereumTesterProvider(ethereum_tester=eth_tester)

    # Use the the custom provider and registrar to init an interface
    circumflex = DeployerCircumflex(compiler=solidity_compiler,    # freshly recompile
                                    registry=temp_registrar,       # use temporary registrar
                                    providers=(pyevm_provider, ))  # use custom test provider

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


@pytest.fixture(scope="module")
def non_ursula_miners(three_agents):
    token_agent, miner_agent, policy_agent = three_agents
    etherbase, alice, bob, *all_yall = token_agent.blockchain.interface.w3.eth.accounts

    ursula_addresses = all_yall[:int(constants.NUMBER_OF_URSULAS_IN_NETWORK)]

    _receipts = token_airdrop(token_agent=token_agent, origin=etherbase,
                              addresses=all_yall, amount=1000000 * constants.M)

    starting_point = constants.URSULA_PORT_SEED + 500

    _ursulas = make_ursulas(ether_addresses=ursula_addresses,
                            ursula_starting_port=int(starting_point),
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
