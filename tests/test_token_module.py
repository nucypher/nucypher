from pytest import raises
from populus.contracts.exceptions import NoKnownAddress

from nkms_eth import token


def test_create(chain):
    t = token.create()
    assert len(t.address) == 42


def test_get(chain):
    with raises(NoKnownAddress):
        token.get()

    token.create()
    t = token.get()
    assert len(t.address) == 42


def test_escrow_create(chain):
    token.create()
    with raises(NoKnownAddress):
        token.escrow()
    e1 = token.create_escrow()
    e2 = token.escrow()

    assert len(e1.address) == 42
    assert e1.address == e2.address
