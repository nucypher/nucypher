import pytest

from nkms_eth.agents import NuCypherKMSTokenAgent, MinerAgent
from nkms_eth.blockchain import TheBlockchain
from nkms_eth.deployers import NuCypherKMSTokenDeployer
from tests.utilities import TesterBlockchain, MockMinerEscrowDeployer


@pytest.fixture(scope='function')
def testerchain():
    chain = TesterBlockchain()
    yield chain
    del chain
    TheBlockchain._TheBlockchain__instance = None


@pytest.fixture(scope='function')
def token_deployer(testerchain):
    token_deployer = NuCypherKMSTokenDeployer(blockchain=testerchain)
    token_deployer.arm()
    token_deployer.deploy()
    yield token_deployer


@pytest.fixture(scope='function')
def token_agent(testerchain):
    token = NuCypherKMSTokenAgent(blockchain=testerchain)
    yield token


@pytest.fixture(scope='function')
def escrow_deployer(token_agent):
    escrow = MockMinerEscrowDeployer(token_agent)
    escrow.arm()
    escrow.deploy()
    yield escrow


@pytest.fixture(scope='function')
def miner_agent(token_agent):
    miner_agent = MinerAgent(token_agent)
    yield miner_agent