import os
import pytest
import tempfile

from nkms.blockchain.eth.agents import NuCypherKMSTokenAgent, MinerAgent
from nkms.blockchain.eth.agents import PolicyAgent
from nkms.blockchain.eth.chains import TheBlockchain, TesterBlockchain
from nkms.blockchain.eth.deployers import PolicyManagerDeployer, NuCypherKMSTokenDeployer
from nkms.blockchain.eth.utilities import MockMinerEscrowDeployer
from nkms.blockchain.eth.interfaces import Registrar, Provider


@pytest.fixture(scope='session')
def tester_registrar():
    _, filepath = tempfile.mkstemp()
    tester_registrar = Registrar(chain_name='tester', registrar_filepath=filepath)
    yield tester_registrar
    os.remove(filepath)


@pytest.fixture(scope='session')
def tester_provider(tester_registrar):
    tester_provider = Provider(registrar=tester_registrar)
    yield tester_provider


@pytest.fixture(scope='session')
def chain(tester_provider):

    chain = TesterBlockchain(provider=tester_provider)
    yield chain

    del chain
    TheBlockchain._TheBlockchain__instance = None


@pytest.fixture(scope='session')
def web3(chain):
    yield chain.provider.web3


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
