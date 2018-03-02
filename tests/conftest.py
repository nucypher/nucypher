import pytest
from nkms_eth.blockchain import TesterBlockchain, Blockchain
from nkms_eth.token import NuCypherKMSToken
from nkms_eth.escrow import Escrow
from nkms_eth.miner import Miner


@pytest.fixture(scope='function')
def testerchain():
    chain = TesterBlockchain()
    yield chain
    del chain
    Blockchain._instance = False


@pytest.fixture(scope='function')
def token(testerchain):
    token = NuCypherKMSToken(blockchain=testerchain)
    token.arm()
    token.deploy()
    yield token


@pytest.fixture(scope='function')
def escrow(testerchain, token):
    escrow = Escrow(blockchain=testerchain, token=token)
    escrow.arm()
    escrow.deploy()
    yield escrow