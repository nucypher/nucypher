import pytest
from nkms_eth.blockchain import TesterBlockchain
from nkms_eth.token import NuCypherKMSToken
from nkms_eth.escrow import Escrow
from nkms_eth.miner import Miner


@pytest.fixture(scope='function')
def testerchain():
    chain = TesterBlockchain()
    yield chain


@pytest.fixture(scope='function')
def token(testerchain):
    token = NuCypherKMSToken(blockchain=testerchain)
    token.arm().deploy()
    yield token


@pytest.fixture(scope='function')
def escrow(testerchain, token):
    escrow = Escrow(blockchain=testerchain, token=token)
    escrow.arm().deploy()
    return escrow