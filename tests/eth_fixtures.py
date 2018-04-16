import os
import tempfile

import pytest
from eth_tester import EthereumTester, PyEVMBackend
from web3 import EthereumTesterProvider
from web3.contract import Contract

from nkms.blockchain.eth.agents import NuCypherKMSTokenAgent, MinerAgent
from nkms.blockchain.eth.agents import PolicyAgent
from nkms.blockchain.eth.chains import TheBlockchain, TesterBlockchain
from nkms.blockchain.eth.deployers import PolicyManagerDeployer, NuCypherKMSTokenDeployer
from nkms.blockchain.eth.interfaces import Registrar, ContractProvider
from nkms.blockchain.eth.sol.compile import SolidityCompiler
from nkms.blockchain.eth.utilities import MockMinerEscrowDeployer


@pytest.fixture(scope='session')
def sol_compiler():
    compiler = SolidityCompiler()
    yield compiler


@pytest.fixture(scope='module')
def tester_registrar():
    _, filepath = tempfile.mkstemp()
    tester_registrar = Registrar(chain_name='tester', registrar_filepath=filepath)
    yield tester_registrar
    os.remove(filepath)


@pytest.fixture(scope='module')
def tester_provider(tester_registrar, sol_compiler):
    """
    Provider backend
    https: // github.com / ethereum / eth - tester     # available-backends
    """
    eth_tester = EthereumTester(backend=PyEVMBackend())
    test_provider = EthereumTesterProvider(ethereum_tester=eth_tester)  # , api_endpoints=None)

    tester_provider = ContractProvider(provider_backend=test_provider,
                                       registrar=tester_registrar,
                                       sol_compiler=sol_compiler)
    yield tester_provider


@pytest.fixture(scope='module')
def web3(tester_provider):
    yield tester_provider.w3


@pytest.fixture(scope='module')
def chain(tester_provider):
    chain = TesterBlockchain(contract_provider=tester_provider)
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
def mock_policy_manager_deployer(mock_token_deployer):
    policy_manager_deployer = PolicyManagerDeployer(token_deployer=mock_token_deployer)
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


@pytest.fixture()
def token(web3, chain):
    creator = web3.eth.accounts[0]
    # Create an ERC20 token
    token, _ = chain.provider.get_or_deploy_contract('NuCypherKMSToken', int(2e9))
    return token


@pytest.fixture()
def escrow_contract(web3, chain, token):
    creator = web3.eth.accounts[0]
    # Creator deploys the escrow

    contract, _ = chain.provider.get_or_deploy_contract(
        'MinersEscrow', token.address, 1, int(8e7), 4, 4, 2, 100, int(1e9)
    )

    dispatcher, _ = chain.provider.deploy_contract('Dispatcher', contract.address)

    # Deploy second version of the government contract
    contract = web3.eth.contract(contract.abi, dispatcher.address, ContractFactoryClass=Contract)
    return contract
