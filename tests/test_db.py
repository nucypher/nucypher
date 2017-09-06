from nkms.db import DB
import pytest


def test_db():
    db = DB()
    db[b'x'] = b'y'
    assert db[b'x'] == b'y'
    db.close()

    db2 = DB()
    assert b'x' in db2
    assert db2[b'x'] == b'y'
    del db2[b'x']
    db2.close()

    db = DB()
    with pytest.raises(KeyError):
        db[b'x']
    assert b'x' not in db
    db.close()

    assert db.path == db2.path


def test_store_dict():
    db = DB()
    db[b'x'] = {b'a': 1, b'b': 2}
    assert db[b'x'][b'a'] == 1
    db.close()
