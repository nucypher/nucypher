from pytest import raises
from populus.contracts.exceptions import NoKnownAddress

from nkms_eth.blockchain import TesterBlockchain
from nkms_eth.token import NuCypherKMSToken


def test_get_token_before_creation(testerchain):
    with raises(NoKnownAddress):
        NuCypherKMSToken.get(blockchain=testerchain)


def test_create_nucypher_kms_token(testerchain):
    token = NuCypherKMSToken(blockchain=testerchain)
    assert len(token.contract.address) == 42
    assert token.contract.call().totalSupply() != 0
    assert token.contract.call().totalSupply() == 1000000000000000000000000000


def test_create_then_get_nucypher_kms_token(testerchain):

    with raises(NoKnownAddress):
        NuCypherKMSToken.get(blockchain=testerchain)

    token = NuCypherKMSToken(blockchain=testerchain)

    assert len(token.contract.address) == 42
    assert token.contract.call().totalSupply() != 0
    assert token.contract.call().totalSupply() == 1000000000000000000000000000

    same_token = NuCypherKMSToken.get(blockchain=testerchain)

    assert token.contract.address == same_token.contract.address
    assert token == same_token



