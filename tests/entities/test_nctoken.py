from pytest import raises
from populus.contracts.exceptions import NoKnownAddress

from nkms_eth.blockchain import TesterBlockchain
from nkms_eth.token import NuCypherKMSToken


def test_create_and_get_nucypherkms_token(testerchain):
    with raises(NoKnownAddress):
        NuCypherKMSToken.get(blockchain=testerchain)

    token = NuCypherKMSToken(blockchain=testerchain)
    token.arm()
    token.deploy()

    assert len(token.contract.address) == 42
    assert token.contract.call().totalSupply() != 0
    # assert token.contract.call().totalSupply() == 10 ** 9 - 1

    same_token = NuCypherKMSToken.get(blockchain=testerchain)

    assert token.contract.address == same_token.contract.address
    assert token == same_token


