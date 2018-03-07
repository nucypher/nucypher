import pytest

from nkms_eth.agents import NuCypherKMSTokenAgent
from nkms_eth.deployers import NuCypherKMSTokenDeployer
from tests.utilities import TesterBlockchain, MockMinerEscrow


@pytest.fixture(scope='function')
def testerchain():
    chain = TesterBlockchain()
    yield chain
    del chain
    TesterBlockchain.__instance = None


@pytest.fixture(scope='function')
def token_agent(testerchain):
    token = NuCypherKMSTokenAgent(blockchain=testerchain)
    yield token

@pytest.fixture(scope='function')
def token_deployer(testerchain):
    token_deployer = NuCypherKMSTokenDeployer(blockchain=testerchain)
    token_deployer.arm()
    token_deployer.deploy()
    yield token_deployer


@pytest.fixture(scope='function')
def escrow(testerchain, token):
    escrow = MockMinerEscrow(blockchain=testerchain, token=token)
    escrow.arm()
    escrow.deploy()
    yield escrow