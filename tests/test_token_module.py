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
