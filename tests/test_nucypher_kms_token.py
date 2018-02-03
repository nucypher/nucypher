from pytest import raises
from populus.contracts.exceptions import NoKnownAddress
from nkms_eth.token import NuCypherKMSToken


def test_get(testerchain):
    with raises(NoKnownAddress):
        NuCypherKMSToken.get(blockchain=testerchain)

    token = NuCypherKMSToken(blockchain=testerchain)
    assert len(token.contract.address) == 42
