from pytest import raises
from populus.contracts.exceptions import NoKnownAddress
from nkms_eth import token
from nkms_eth import escrow


def test_escrow_create(chain):
    token.create()
    with raises(NoKnownAddress):
        escrow.get()
    e1 = escrow.create()
    e2 = escrow.get()

    assert len(e1.address) == 42
    assert e1.address == e2.address
