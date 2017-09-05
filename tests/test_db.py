from nkms.db import DB
import shutil
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

    assert db.path == db2.path

    shutil.rmtree(db.path)
