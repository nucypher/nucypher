import pytest

from nkms_eth import utilities as utils
from nkms_eth.blockchain import TheBlockchain
from nkms_eth.agents import NuCypherKMSTokenAgent, MinerAgent


@pytest.fixture(scope='function')
def testerchain():
    chain = utils.TesterBlockchain()
    yield chain
    del chain
    TheBlockchain._TheBlockchain__instance = None


@pytest.fixture(scope='function')
def mock_token_deployer(testerchain):
    token_deployer = utils.MockNuCypherKMSTokenDeployer(blockchain=testerchain)
    token_deployer.arm()
    token_deployer.deploy()
    yield token_deployer


@pytest.fixture(scope='function')
def mock_miner_escrow_deployer(token_agent):
    escrow = utils.MockMinerEscrowDeployer(token_agent)
    escrow.arm()
    escrow.deploy()
    yield escrow


@pytest.fixture(scope='function')
def token_agent(testerchain, mock_token_deployer):
    token = NuCypherKMSTokenAgent(blockchain=testerchain)
    yield token


@pytest.fixture(scope='function')
def mock_miner_agent(token_agent, mock_token_deployer, mock_miner_escrow_deployer):
    miner_agent = MinerAgent(token_agent)
    yield miner_agent
