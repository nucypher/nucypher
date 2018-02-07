import pytest
from nkms_eth.blockchain import TesterBlockchain
from nkms_eth.token import NuCypherKMSToken
from nkms_eth.escrow import Escrow
from nkms_eth.miner import Miner


@pytest.fixture()
def testerchain():
    chain = TesterBlockchain()
    yield chain

@pytest.fixture()
def token(testerchain):
    return NuCypherKMSToken(blockchain=testerchain)


@pytest.fixture()
def escrow(testerchain, token):
    return Escrow(blockchain=testerchain, token=token)


@pytest.fixture()
def miner(testerchain, escrow, token):
    return Miner(blockchain=testerchain, token=token, escrow=escrow)
