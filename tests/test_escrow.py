from populus.contracts.exceptions import NoKnownAddress
from pytest import raises

from nkms_eth.escrow import Escrow
from nkms_eth.token import NuCypherKMSToken


def test_create_escrow(testerchain):
    with raises(NoKnownAddress):
        NuCypherKMSToken.get(blockchain=testerchain)
    token = NuCypherKMSToken(blockchain=testerchain)
    same_token = NuCypherKMSToken.get(blockchain=testerchain)

    assert len(token.contract.address) == 42
    assert token.contract.address == same_token.contract.address

    with raises(NoKnownAddress):
        Escrow.get(blockchain=testerchain, token=token)
    escrow = Escrow(blockchain=testerchain, token=token)
    same_escrow = Escrow.get(blockchain=testerchain, token=token)

    assert len(escrow.contract.address) == 42
    assert escrow.contract.address == same_escrow.contract.address