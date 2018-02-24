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
    token = NuCypherKMSToken(blockchain=testerchain)
    token.arm().deploy()
    return token


@pytest.fixture()
def escrow(testerchain, token):
    escrow = Escrow(blockchain=testerchain, token=token)
    escrow.arm().deploy()
    return escrow


@pytest.fixture()
def miner(testerchain, escrow, token):
    address = testerchain.web3.eth.accounts[1]
    return Miner(blockchain=testerchain, token=token, escrow=escrow, address=address)
