from populus.contracts.exceptions import NoKnownAddress
from pytest import raises

from nkms_eth.escrow import Escrow
from nkms_eth.token import NuCypherKMSToken


def test_create_escrow(testerchain, token):
    # token = NuCypherKMSToken(blockchain=testerchain)

    with raises(NoKnownAddress):
        Escrow.get(blockchain=testerchain, token=token)

    e1 = Escrow(blockchain=testerchain, token=token)
    e2 = Escrow.get(blockchain=testerchain, token=token)

    assert len(e1.contract.address) == 42
    assert e1.contract.address == e2.contract.addresst.address == e2.contract.address